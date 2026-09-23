"""Klinik WhatsApp — hastaya giden mesajların GERÇEKTEN gönderilmesi.

Önceki durum: gelen WhatsApp mesajı işleniyor, cevap üretiliyordu; ama cevap
yalnız veritabanına `"delivery": "simulated"` diye yazılıyordu. Meta ve Twilio
webhook'un HTTP cevabını hastaya iletmez — hasta hiçbir cevap almıyordu. KVKK
aydınlatma metni de WhatsApp'tan yazan hastaya hiç ulaşmıyordu.

Akış:
1. Hastaya gidecek mesaj oluşturulurken `"delivery": "pending"` işaretlenir —
   YALNIZ gerçek webhook'tan gelen konuşmalarda (`deliver_reply=True`).
   Operatörün panel simülasyonu işaretlemez; eski "simulated" kayıtlara
   dokunulmaz, hasta yeniden yazınca geçmiş cevaplar toptan gönderilmez.
2. `flush` bekleyenleri sıraya koyar:
     gönderim kapalı          → demo_only
     24 saat penceresi kapalı → blocked_no_template (şablon: bkz. madde B)
     aksi halde               → queued + outbox olayı
3. Worker gönderir → accepted (sağlayıcı kabul etti — TESLİM DEĞİL). Teslim,
   okundu, başarısız sonradan durum bildirimiyle gelir. Başarısızsa konuşma
   insana düşer: hasta cevap almadıysa bunu bir insan görmeli.

Cevap, mesajın GELDİĞİ işletme numarasından gider (konuşmada saklanır): çok
klinikli kurulumda bir kliniğin hastasına başka kliniğin numarasından yazılmaz.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.channels import whatsapp_meta as meta
from app.channels import whatsapp_twilio as twilio
from app.core.config import get_settings
from app.models import (
    ClinicChannel,
    ClinicConversation,
    ClinicConversationStatus,
    ClinicMessage,
    ClinicMessageSender,
)
from app.services.outbox_service import enqueue_outbox_event

logger = logging.getLogger('cognivault.clinic.whatsapp')

OUTBOX_EVENT = 'clinic.whatsapp.send'
WINDOW = timedelta(hours=24)
PENDING = 'pending'
UNDELIVERABLE = {'failed', 'blocked_no_template'}
# Durum yalnız ileri gider; sağlayıcı bildirimleri sıra dışı gelebilir.
ORDER = {'queued': 0, 'accepted': 1, 'sent': 2, 'delivered': 3, 'read': 4}
TWILIO_STATUS = {'queued': 'queued', 'accepted': 'accepted', 'sending': 'accepted', 'sent': 'sent',
                 'delivered': 'delivered', 'read': 'read', 'failed': 'failed', 'undelivered': 'failed'}

SHADOW_ACK = ('Mesajınızı aldım ve hekimimize ilettim; inceleyip size buradan dönecek. '
              'Tıbbi konularda hekim onayı olmadan kesin yönlendirme yapmıyorum.')
EMERGENCY_ACK = ('Belirttiğiniz durum acil olabilir. Lütfen hemen 112’yi arayın ya da en yakın acil '
                 'servise başvurun. Mesajınızı hekimimize öncelikli olarak ilettim.')


def delivery_marker(deliver: bool) -> str:
    """Mesaj oluşturulurken yazılacak teslim işareti."""
    return PENDING if deliver else 'simulated'


def conversation_delivers(conversation: ClinicConversation) -> bool:
    """Bu konuşmaya sonradan (ör. hekim onayı) yazılan mesaj hastaya gitmeli mi?
    Yalnız gerçek webhook'tan gelmiş, gönderim rotası saklanmış konuşmalar."""
    return conversation.channel == ClinicChannel.WHATSAPP and bool(
        (conversation.metadata_json or {}).get('whatsapp_route'))


def remember_route(conversation: ClinicConversation, *, provider: str, business: str) -> None:
    """Hastanın yazdığı işletme numarasını sakla — cevap oradan gidecek."""
    route = {'provider': provider, 'business': business}
    if (conversation.metadata_json or {}).get('whatsapp_route') != route:
        conversation.metadata_json = {**(conversation.metadata_json or {}), 'whatsapp_route': route}


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _window_open(db: Session, conversation: ClinicConversation, now: datetime) -> bool:
    last = _aware(db.scalar(select(func.max(ClinicMessage.created_at)).where(
        ClinicMessage.conversation_id == conversation.id,
        ClinicMessage.sender == ClinicMessageSender.PATIENT)))
    return last is not None and now - last < WINDOW


def _set_delivery(message: ClinicMessage, status: str, *, error: str | None = None, **extra) -> None:
    meta_json = dict(message.metadata_json or {})
    meta_json['delivery'] = status
    if error is not None:
        meta_json['delivery_error'] = error[:300]
    meta_json.update(extra)
    message.metadata_json = meta_json


def flush(db: Session, conversation: ClinicConversation, *, now: datetime | None = None) -> list[ClinicMessage]:
    """Konuşmadaki bekleyen (pending) mesajları gönderim sırasına koyar ve commit eder."""
    now = now or datetime.now(timezone.utc)
    settings = get_settings()
    route = (conversation.metadata_json or {}).get('whatsapp_route')
    rows = db.scalars(select(ClinicMessage).where(
        ClinicMessage.conversation_id == conversation.id,
    ).order_by(ClinicMessage.id).with_for_update(skip_locked=True)).all()
    pending = [m for m in rows if (m.metadata_json or {}).get('delivery') == PENDING]
    if not pending:
        return []
    window = _window_open(db, conversation, now)
    failed = False
    for message in pending:
        # Hatırlatma gibi yedeği (SMS) olan mesajlar başarısızlıkta konuşmayı
        # insana düşürmez; yedeği çağıran uygular.
        escalate = (message.metadata_json or {}).get('escalate_on_failure', True)
        provider = (route or {}).get('provider')
        form = 'session' if window else ('template' if template_ready(message, provider) else None)
        if not settings.clinic_whatsapp_send_enabled:
            _set_delivery(message, 'demo_only', delivery_provider=provider, form=form or 'session')
        elif not route:
            _set_delivery(message, 'failed', error='Gönderim rotası yok (hangi işletme numarasından?)')
            failed = failed or escalate
        elif form is None:
            _set_delivery(message, 'blocked_no_template', delivery_provider=provider,
                          error='24 saat penceresi kapalı; onaylı şablon gerekir')
            failed = failed or escalate
        else:
            event = enqueue_outbox_event(db, event_type=OUTBOX_EVENT, payload={'message_id': message.id},
                                         organization_id=None, clinic_id=message.clinic_id)
            _set_delivery(message, 'queued', delivery_provider=provider, outbox_event_id=event.id, form=form)
        db.add(message)
    if failed:
        _needs_human(conversation, 'WhatsApp mesajı hastaya gönderilemedi')
        db.add(conversation)
    db.commit()
    return pending


# Şablon türü → sağlayıcıdaki onaylı şablonun ayar anahtarı.
TEMPLATE_SETTINGS = {
    'reminder': {'meta': 'clinic_wa_template_reminder', 'twilio': 'clinic_twilio_reminder_content_sid'},
}


def template_ready(message: ClinicMessage, provider: str | None) -> bool:
    template = (message.metadata_json or {}).get('template') or {}
    key = TEMPLATE_SETTINGS.get(template.get('kind'), {}).get(provider or '')
    return bool(key and getattr(get_settings(), key, ''))


def _needs_human(conversation: ClinicConversation, reason: str) -> None:
    conversation.status = ClinicConversationStatus.WAITING_HUMAN
    conversation.metadata_json = {**(conversation.metadata_json or {}), 'whatsapp_delivery_problem': reason}


def _patient_address(conversation: ClinicConversation) -> str:
    phone = conversation.patient.phone if conversation.patient else ''
    phone = (phone or '').removeprefix('whatsapp:')
    # Meta numarayı başında + olmadan verir ("90532…"); Twilio "+90532…".
    return phone if phone.startswith('+') else f'+{phone}'


def send_message(db: Session, message: ClinicMessage) -> None:
    """Tek bir kuyruktaki mesajı sağlayıcıya iletir (worker çağırır)."""
    settings = get_settings()
    conversation = db.get(ClinicConversation, message.conversation_id)
    route = (conversation.metadata_json or {}).get('whatsapp_route') or {}
    to = _patient_address(conversation)
    info = message.metadata_json or {}
    buttons = [tuple(b) for b in info.get('buttons') or []]
    template = info.get('template') or {}
    names = TEMPLATE_SETTINGS.get(template.get('kind'), {})
    try:
        if route.get('provider') == 'meta':
            if info.get('form') == 'template':
                content = meta.template_content(
                    name=getattr(settings, names['meta']), language=settings.clinic_wa_template_language,
                    params=template.get('params') or [], quick_replies=template.get('quick_replies') or [])
            elif buttons:
                content = meta.buttons_content(message.content, buttons)
            else:
                content = meta.text_content(message.content)
            provider_id = meta.send(meta.envelope(to, content),
                                    phone_number_id=route['business'], access_token=settings.meta_access_token)
        elif route.get('provider') == 'twilio':
            base = settings.clinical_webhook_base_url.strip().rstrip('/')
            common = dict(to=to, from_=route['business'], account_sid=settings.twilio_account_sid,
                          auth_token=settings.twilio_auth_token,
                          status_callback=f'{base}{settings.api_prefix}/webhooks/whatsapp/status' if base else None)
            if info.get('form') == 'template':
                provider_id = twilio.send_content(
                    content_sid=getattr(settings, names['twilio']),
                    variables={str(i + 1): p for i, p in enumerate(template.get('params') or [])}, **common)
            else:
                # Twilio'da serbest mesaj düğme taşıyamaz: seçenekleri yazıyla söyle
                # (yazılı yanıtlar da tanınır).
                body = message.content
                if buttons:
                    body += '\n\n' + ' / '.join(title for _, title in buttons) + ' yazarak yanıtlayabilirsiniz.'
                provider_id = twilio.send_text(body=body, **common)
        else:
            raise meta.PermanentSendError('Bilinmeyen sağlayıcı')
    except (meta.PermanentSendError, ValueError) as exc:
        _set_delivery(message, 'failed', error=str(exc))
        if info.get('escalate_on_failure', True):
            _needs_human(conversation, 'WhatsApp mesajı hastaya gönderilemedi')
        db.add_all([message, conversation])
        db.commit()
        logger.warning('clinic.whatsapp.send_failed', extra={'message_id': message.id})
        return
    message.external_message_id = provider_id
    _set_delivery(message, 'accepted')
    db.add(message)
    db.commit()


def make_delivery_handler(session_factory):
    """Outbox handler. Ağ/5xx hatası yükselir → outbox tekrar dener; kalıcı ret
    tekrar denenmez, mesaj `failed` olur ve konuşma insana düşer."""
    def deliver(event) -> None:
        message_id = (event.payload_json or {}).get('message_id')
        with session_factory() as db:
            message = db.get(ClinicMessage, message_id)
            if message is None or (message.metadata_json or {}).get('delivery') != 'queued':
                return
            send_message(db, message)
    return deliver


def meta_statuses(payload: dict) -> list[tuple[str, str, str]]:
    """Meta webhook gövdesindeki teslim bildirimleri: (mesaj kimliği, durum, hata)."""
    found = []
    for entry in payload.get('entry') or []:
        for change in entry.get('changes') or []:
            for status in (change.get('value') or {}).get('statuses') or []:
                if status.get('id') and status.get('status'):
                    errors = status.get('errors') or [{}]
                    detail = errors[0].get('title') or errors[0].get('message') or ''
                    found.append((status['id'], status['status'], str(detail)[:300]))
    return found


def apply_status(db: Session, provider_message_id: str, status: str, error: str = '') -> bool:
    """Sağlayıcı teslim bildirimi. Durum yalnız ileri gider."""
    message = db.scalar(select(ClinicMessage).where(
        ClinicMessage.external_message_id == provider_message_id,
        ClinicMessage.sender != ClinicMessageSender.PATIENT))
    if message is None:
        return False
    current = (message.metadata_json or {}).get('delivery')
    if status == 'failed':
        if current == 'failed':
            return True
        _set_delivery(message, 'failed', error=error or 'Sağlayıcı teslim edemedi')
        conversation = db.get(ClinicConversation, message.conversation_id)
        _needs_human(conversation, 'WhatsApp mesajı hastaya iletilemedi')
        db.add(conversation)
    elif ORDER.get(status, -1) > ORDER.get(current, -1):
        _set_delivery(message, status)
    else:
        return True
    db.add(message)
    db.commit()
    return True
