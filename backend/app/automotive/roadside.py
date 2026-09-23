"""Yol yardımı hattı — telefon ve WhatsApp olaylarını işe, işi çekiciye bağlar.

Müşteri akışı:
    arama / WhatsApp mesajı → iş açılır → eksik bilgi sırayla sorulur
    (sorun · güvenlik · konum · araç · varış yeri · paylaşım izni)
    → en yakın uygun ekibe OTOMATİK teklif → ekip kabul eder (tahmini varış)
    → yola çıktı → ulaştı → (taşıma) → tamamlandı

Durum makinesinin tek sahibi `operations.apply`'dır; bu modül kanal olaylarını
eyleme çevirir ve kime ne söyleneceğine karar verir.

Değişmezler:
- "Çekici yola çıktı" yalnız ekip "Yola çıktım" dediğinde söylenir. Teklif
  yapıldı ≠ kabul edildi ≠ yola çıktı; müşteriye her biri ayrı söylenir.
- Acil sinyal (yaralı, yangın, sıkıştı…) her aşamada akışı keser: 112 ve insan.
- Ekip yanıtı yalnız AYARLARDA tanımlı ekip numarasından ve yalnız o ekibe
  atanmış iş için kabul edilir — müşteri "kabul" butonu taklit edemez.
- Durum değişikliği ile giden mesajlar tek işlemde yazılır (outbox): ya ikisi
  birden ya hiçbiri.
- WhatsApp 24 saat kuralı: pencere kapalıyken serbest mesaj gitmez, onaylı
  şablon gider; şablon yoksa "gönderildi" denmez, iş danışmana düşer.
"""
from __future__ import annotations

import hashlib
import json
import logging
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.text_understanding import normalize_for_intent
from app.automotive import operations as ops
from app.automotive import whatsapp as wa
from app.core.config import get_settings
from app.models import AutomotiveCase, AutomotiveMessage, User
from app.services.outbox_service import enqueue_outbox_event

logger = logging.getLogger('cognivault.automotive.roadside')

OUTBOX_EVENT = 'automotive.whatsapp.send'
# Ekip bu sürede kabul etmezse teklif düşer, sıradaki ekibe geçilir. Teslim
# edilemeyen teklifi ve telefona bakmayan şoförü aynı mekanizma yakalar.
OFFER_TIMEOUT = timedelta(minutes=5)
ONSITE = 'Yerinde müdahale'
TOW_CAPABILITIES = {'flatbed', 'ev_flatbed'}
WINDOW = timedelta(seconds=wa.SESSION_WINDOW_SECONDS)


# ─── Anlama (saf) ────────────────────────────────────────────────────────────

# Sıra önemli, ilk eşleşen kazanır: "kaza yaptım çekici lazım" → kaza (güvenlik
# önceliği); "aracım çalışmıyor çekici lazım" → çekici (açık istek, akü sanılmaz).
SERVICE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ('accident', ('kaza', 'carpis', 'carpt', 'hasar', 'devrildi', 'takla')),
    ('ev', ('elektrikli', 'sarj bitti', 'sarji bitti', 'sarjim')),
    ('tow', ('cekici', 'cektir', 'kurtarici', 'tasiyici')),
    ('fuel', ('benzin', 'yakit', 'mazot', 'dizel', 'motorin', 'lpg')),
    ('tire', ('lastik', 'patla', 'patlak', 'stepne')),
    ('locked', ('anahtar', 'kilitli', 'kilit kald', 'kapi acilm')),
    ('battery', ('aku', 'mars', 'calismiyor', 'calismadi', 'kontak')),
    ('complaint', ('sikayet', 'ayni sorun', 'duzelmedi', 'hala ayni')),
    ('status', ('hazir mi', 'ne durumda', 'ne zaman biter', 'bitti mi')),
    ('quote', ('fiyat', 'teklif', 'ne kadar', 'ucret')),
    ('pickup', ('vale', 'adresimden', 'gelip alin', 'evden alin')),
    ('fleet', ('filo', 'sirket arac', 'araclarimiz')),
    ('inspection', ('muayene', 'tuvturk')),
    ('maintenance', ('bakim', 'yag degis', 'periyodik')),
    ('repair', ('ses yap', 'ariza', 'isik yan', 'titre', 'kontrol')),
)
EMERGENCY = ('yarali', 'yaralan', 'yangin', 'yaniyor', 'alev', 'duman cik', 'sikisti',
             'sikistim', 'nefes alam', 'kanama', 'kaniyor', 'bayild', 'bilinci', 'kalp')
CANCEL = ('iptal', 'vazgectim', 'gerek kalmadi', 'hallettim', 'hallettik')
HUMAN = ('temsilci', 'insanla', 'danisman', 'yetkili', 'operator')
WHERE = ('nerede', 'kac dakika', 'ne zaman gelecek', 'geliyor mu', 'ne kadar kald')


def detect_service(text: str) -> str | None:
    n = normalize_for_intent(text)
    for service_id, words in SERVICE_KEYWORDS:
        if any(w in n for w in words):
            return service_id
    return None


def is_emergency(text: str) -> bool:
    n = normalize_for_intent(text)
    return any(w in n for w in EMERGENCY)


def contact_key(phone: str) -> str:
    return hashlib.sha256(phone.encode('utf-8')).hexdigest()


def mask_phone(phone: str | None) -> str:
    if not phone or len(phone) < 7:
        return ''
    return phone[:4] + '•' * (len(phone) - 8) + phone[-4:]


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _now(now: datetime | None = None) -> datetime:
    return now or datetime.now(timezone.utc)


# ─── Yapılandırma ────────────────────────────────────────────────────────────


def team_phones() -> dict[str, str]:
    """Ayarlardaki ekip numaraları. Geçersiz kayıt sessizce yok sayılmaz — loglanır."""
    raw = get_settings().automotive_team_phones.strip()
    if not raw:
        return {}
    try:
        mapping = json.loads(raw)
    except ValueError:
        logger.error('automotive.team_phones.invalid_json')
        return {}
    known = {t['id'] for t in ops.TEAMS}
    result = {}
    for team_id, phone in (mapping or {}).items():
        if team_id in known and isinstance(phone, str) and wa.E164.fullmatch(phone):
            result[team_id] = phone
        else:
            logger.error('automotive.team_phones.rejected', extra={'team_id': team_id})
    return result


def team_for_phone(phone: str) -> str | None:
    return next((tid for tid, p in team_phones().items() if p == phone), None)


def inbound_owner(db: Session) -> User:
    email = get_settings().automotive_inbound_owner_email.strip().lower()
    if not email:
        raise HTTPException(503, 'Gelen kanal sahibi (AUTOMOTIVE_INBOUND_OWNER_EMAIL) tanımlı değil.')
    user = db.scalar(select(User).where(func.lower(User.email) == email, User.is_active.is_(True)))
    if user is None:
        raise HTTPException(503, 'Gelen kanal sahibi hesabı bulunamadı veya pasif.')
    return user


# ─── Giden mesaj ─────────────────────────────────────────────────────────────


@dataclass
class Outgoing:
    audience: str                      # customer | team:<id>
    purpose: str
    body: str                          # panelde görünen okunur metin
    session: dict | None = None        # açık pencerede gidecek içerik
    template: tuple[str, list[str], list[str]] | None = None  # (ayar anahtarı, parametreler, hızlı yanıtlar)


@dataclass
class Result:
    case: dict | None
    replies: list[str] = field(default_factory=list)   # müşteriye söylenen metinler


def _say(audience: str, purpose: str, body: str, *, buttons: list[tuple[str, str]] | None = None,
         template: tuple[str, list[str], list[str]] | None = None) -> Outgoing:
    session = wa.buttons_content(body, buttons) if buttons else wa.text_content(body)
    return Outgoing(audience, purpose, body, session=session, template=template)


def _window_open(db: Session, *, case_id: str | None, owner_id: int, audience: str, now: datetime) -> bool:
    query = select(func.max(AutomotiveMessage.created_at)).where(
        AutomotiveMessage.owner_id == owner_id, AutomotiveMessage.direction == 'in',
        AutomotiveMessage.audience == audience)
    if case_id is not None:  # müşteri penceresi bu işe, ekip penceresi ekibe bağlı
        query = query.where(AutomotiveMessage.case_id == case_id)
    last = _aware(db.scalar(query))
    return last is not None and now - last < WINDOW


def _queue(db: Session, owner: User, row: AutomotiveCase, data: dict, out: Outgoing, now: datetime) -> AutomotiveMessage:
    settings = get_settings()
    if out.audience == 'customer':
        to = data.get('contact')
        window = _window_open(db, case_id=row.id, owner_id=owner.id, audience='customer', now=now)
    else:
        to = team_phones().get(out.audience.split(':', 1)[1])
        window = _window_open(db, case_id=None, owner_id=owner.id, audience=out.audience, now=now)

    template_name = getattr(settings, out.template[0], '') if out.template else ''
    error = None
    if window and out.session is not None:
        form, content = 'session', out.session
    elif template_name:
        _, params, replies = out.template
        form = 'template'
        content = wa.template_content(name=template_name, language=settings.automotive_wa_template_language,
                                      params=params, quick_replies=replies)
    else:
        form, content = 'session', out.session
        error = '24 saat penceresi kapalı ve onaylı şablon tanımlı değil'

    if not settings.automotive_whatsapp_enabled:
        status = 'demo_only'
    elif error:
        status = 'blocked_no_template'
    elif not to:
        status, error = 'failed', 'Alıcı numarası tanımlı değil'
    else:
        status = 'queued'

    # Panel ve simülatör için: şablonla gitse bile müşterinin/ekibin göreceği
    # seçenekler oturum içeriğinden okunur (şablon içeriği başlık taşımaz).
    interactive = (out.session or {}).get('interactive') or {}
    buttons = [[b['reply']['id'], b['reply']['title']] for b in interactive.get('action', {}).get('buttons', [])]
    if form == 'template' and out.template and out.template[2] and not buttons:
        buttons = [[reply_id, 'Konum göndereceğim'] for reply_id in out.template[2]]
    message = AutomotiveMessage(
        id=str(uuid4()), case_id=row.id, owner_id=owner.id, direction='out', audience=out.audience,
        purpose=out.purpose, form=form, body=out.body[:2000],
        payload={'to': to, 'content': content, 'buttons': buttons,
                 'location_request': interactive.get('type') == 'location_request_message'},
        delivery_status=status, error=error, created_at=now, updated_at=now)
    db.add(message)
    if status == 'queued':
        db.flush()
        event = enqueue_outbox_event(db, event_type=OUTBOX_EVENT, payload={'message_id': message.id},
                                     organization_id=owner.organization_id)
        message.outbox_event_id = event.id
    data['messages'].append(dict(role='assistant' if out.audience == 'customer' else 'system',
                                 text=out.body, at=now.isoformat(), audience=out.audience))
    return message


def _record_inbound(db: Session, owner: User, row: AutomotiveCase, inbound: wa.Inbound, audience: str,
                    now: datetime) -> None:
    body = inbound.text or (f'📍 {inbound.latitude:.5f}, {inbound.longitude:.5f} {inbound.address}'.strip()
                            if inbound.kind == 'location' else f'[{inbound.kind}]')
    db.add(AutomotiveMessage(
        id=str(uuid4()), case_id=row.id, owner_id=owner.id, direction='in', audience=audience,
        purpose=inbound.kind, form='inbound', body=body[:2000],
        payload={'reply_id': inbound.reply_id} if inbound.reply_id else None,
        delivery_status='received', provider_message_id=inbound.message_id, created_at=now, updated_at=now))
    db.flush()


def _already_seen(db: Session, message_id: str) -> bool:
    return db.scalar(select(AutomotiveMessage.id).where(AutomotiveMessage.provider_message_id == message_id)) is not None


UNDELIVERABLE = {'failed', 'blocked_no_template'}


def _commit(db: Session, owner: User, row: AutomotiveCase, data: dict, expected_version: int,
            outgoing: list[Outgoing], now: datetime) -> list[AutomotiveMessage]:
    """Durum + giden mesajlar tek işlemde, sonra teslim edilemeyeceği belli
    olan mesajların işe etkisi (commit SONRASI, ayrı işlemde) uygulanır."""
    messages = [_queue(db, owner, row, data, out, now) for out in outgoing]
    data['audit'].append(dict(action='channel', at=now.isoformat(), detail=ops.STATUS_LABELS[data['status']]))
    ops.persist(db, owner, row, data, expected_version=expected_version)
    undeliverable = [m.id for m in messages if m.delivery_status in UNDELIVERABLE]
    if undeliverable:
        handle_failures(db, undeliverable, now=now)
    return messages


def _action(kind: str, version: int, **kwargs) -> ops.Action:
    return ops.Action(event_key=uuid4().hex, version=version, kind=kind, **kwargs)


# ─── İş açma / bulma ─────────────────────────────────────────────────────────


def open_case_for(db: Session, owner: User, phone: str) -> AutomotiveCase | None:
    rows = db.scalars(select(AutomotiveCase).where(
        *ops.scoped(owner), AutomotiveCase.contact_key == contact_key(phone)
    ).order_by(AutomotiveCase.created_at.desc())).all()
    return next((r for r in rows if r.data['status'] not in ops.CLOSED), None)


def _create(db: Session, owner: User, *, phone: str | None, service_id: str, channel: str,
            request_key: str, customer: str, service_confirmed: bool) -> AutomotiveCase:
    existing = db.scalar(select(AutomotiveCase).where(*ops.scoped(owner), AutomotiveCase.request_key == request_key))
    if existing:
        return existing
    data = ops.new_case_data(service_id=service_id, customer=customer or 'Müşteri', channel=channel,
                             fingerprint=ops.digest({'request_key': request_key}))
    data.update(contact=phone, declined_teams=[], priority='normal', offered_at=None,
                intake=dict(service_confirmed=service_confirmed, safety=None, awaiting=''))
    row = AutomotiveCase(id=str(uuid4()), owner_id=owner.id, organization_id=owner.organization_id,
                         request_key=request_key, version=1, data=data,
                         contact_key=contact_key(phone) if phone else None)
    db.add(row)
    db.flush()
    return row


def _set_service(data: dict, service_id: str) -> None:
    data['service'] = service_id
    data['service_title'] = ops.SERVICES[service_id]['title']
    data['intake']['service_confirmed'] = True


# ─── Müşteri: bilgi toplama ──────────────────────────────────────────────────

SAFETY_BUTTONS = [('c:safe:ok', 'Güvendeyiz, kenarda'), ('c:safe:lane', 'Şeritte kaldım'),
                  ('c:safe:danger', 'Yaralı / tehlike var')]
PROBLEM_BUTTONS = [('c:svc:tow', 'Çekici lazım'), ('c:svc:battery', 'Akü / çalışmıyor'),
                   ('c:svc:tire', 'Lastik patladı')]
LANE_ADVICE = ('⚠️ Yol şeridinde kaldıysanız: dörtlüleri yakın, mümkünse araçtan çıkıp bariyerin '
               'arkasına geçin, reflektörü aracın en az 100 metre gerisine koyun. Otoyoldaysanız '
               '112’ye de haber verin. Talebinizi öncelikli işaretledim.')


def _is_tow(data: dict) -> bool:
    return ops.SERVICES[data['service']].get('capability') in TOW_CAPABILITIES


def _location_request() -> Outgoing:
    body = '📍 Konumunuzu paylaşın, ekibimiz tam yerinize gelsin. Aşağıdaki düğmeye dokunmanız yeterli.'
    return Outgoing('customer', 'location_request', body, session=wa.location_request_content(body))


def _next_question(data: dict) -> Outgoing | None:
    """Eksik olan İLK bilgiyi sorar. Müşteri sırayı bozarsa (önce konum atarsa)
    o adım atlanır — sıra dayatılmaz, yalnız eksik olan sorulur."""
    intake = data['intake']
    mobile = ops.SERVICES[data['service']]['mobile']
    settings = get_settings()

    def ask(awaiting: str, out: Outgoing) -> Outgoing:
        intake['awaiting'] = awaiting
        return out

    if not intake['service_confirmed']:
        return ask('problem', _say('customer', 'ask_problem',
                   f'{settings.automotive_brand} hattına hoş geldiniz, nasıl yardımcı olabilirim? '
                   'Aşağıdan seçin ya da kısaca yazın (yakıt, anahtar, kaza, elektrikli araç…).',
                   buttons=PROBLEM_BUTTONS))
    if mobile and intake['safety'] is None:
        return ask('safety', _say('customer', 'ask_safety',
                   'Önce güvenliğiniz: siz ve araçtakiler güvende misiniz, araç nerede duruyor?',
                   buttons=SAFETY_BUTTONS))
    # Konum güvenlikten hemen sonra: yolda kalan biri için en kritik bilgi budur;
    # sohbet yarıda kopsa bile dispeçerin elinde olmalı.
    if mobile and data['location'] is None:
        return ask('location', _location_request())
    if not data['vehicle'] and not intake.get('vehicle'):
        return ask('vehicle', _say('customer', 'ask_vehicle',
                   'Aracınızın plakası ve marka/modeli nedir? (örnek: 34 ABC 123, Fiat Egea)'))
    if mobile and _is_tow(data) and not data['destination'] and not intake.get('destination'):
        return ask('destination', _say('customer', 'ask_destination',
                   f'Aracınızı nereye götürelim? Varsayılan: {settings.automotive_service_name}.',
                   buttons=[('c:dest:service', 'Servisinize'), ('c:dest:other', 'Başka adres')]))
    if mobile and not data['share_permission']:
        return ask('share', _say('customer', 'ask_share',
                   'Konumunuzu size gelecek yardım ekibiyle paylaşalım mı? Yalnız bu iş için kullanılır.',
                   buttons=[('c:share:yes', 'Evet, paylaş'), ('c:share:no', 'Hayır, beni arayın')]))
    intake['awaiting'] = ''
    return None


def _absorb_customer(data: dict, inbound: wa.Inbound, version: int, outgoing: list[Outgoing]) -> None:
    """Gelen müşteri olayını iş verisine işler. Durum geçişleri `ops.apply`'dan geçer."""
    intake = data['intake']
    reply = inbound.reply_id
    text = inbound.text.strip()

    if reply.startswith('c:svc:') and data['status'] == 'intake':
        service_id = reply.split(':', 2)[2]
        if service_id in ops.SERVICES:
            _set_service(data, service_id)
    elif reply == 'c:safe:ok':
        intake['safety'] = 'ok'
    elif reply == 'c:safe:lane':
        intake['safety'] = 'lane'
        data['priority'] = 'high'
        outgoing.append(_say('customer', 'lane_advice', LANE_ADVICE))
    elif reply == 'c:dest:service':
        intake['destination'] = get_settings().automotive_service_name
    elif reply == 'c:dest:other':
        intake['awaiting'] = 'destination_text'
        outgoing.append(_say('customer', 'ask_destination_text', 'Götürülecek adresi yazar mısınız?'))
        return
    elif reply in {'c:share:yes', 'c:share:no'} and data['location']:
        ops.apply(data, _action('share', version, permission=reply == 'c:share:yes'))
        if reply == 'c:share:no':
            ops.apply(data, _action('human', version))
            outgoing.append(_say('customer', 'human', 'Anladım, konumunuzu ekiple paylaşmıyorum. '
                                 'Danışmanımız sizi bu numaradan arayacak.'))
            return
    elif inbound.kind == 'location':
        ops.apply(data, _action('location', version, location=ops.Location(
            latitude=inbound.latitude, longitude=inbound.longitude,
            address=inbound.address, source='whatsapp')))
    elif text:
        awaiting = intake.get('awaiting')
        if awaiting == 'vehicle':
            intake['vehicle'] = text[:120]
        elif awaiting == 'destination_text':
            intake['destination'] = text[:200]
        elif not intake['service_confirmed']:
            service_id = detect_service(text)
            if service_id:
                _set_service(data, service_id)

    # Araç + (mobilse) güvenlik + varış yeri tamamsa ayrıntılar tek eylemle yazılır.
    # "Ayrıntılar yazıldı mı?" durumdan değil araç alanından okunur: müşteri
    # konumu erken atarsa durum `intake`'ten `needs_location`'a geçer ve durum
    # kontrolü ayrıntıları hiç yazdırmazdı.
    mobile = ops.SERVICES[data['service']]['mobile']
    vehicle = intake.get('vehicle')
    destination = intake.get('destination') or (ONSITE if mobile and not _is_tow(data) else '')
    if not data['vehicle'] and data['status'] in {'intake', 'needs_location'} and \
            intake['service_confirmed'] and vehicle and (not mobile or (intake['safety'] and destination)):
        ops.apply(data, _action('details', version, vehicle=vehicle,
                                destination=destination or '', safe=True if mobile else None))
        if not mobile:
            outgoing.append(_say('customer', 'service_requested',
                            f'Talebiniz {get_settings().automotive_service_name} danışmanına iletildi. '
                            'Kesin gün, saat ya da fiyatı danışmanımız servis sisteminden doğrulayıp size dönecek.'))


def handle_customer(db: Session, owner: User, inbound: wa.Inbound, *, now: datetime | None = None) -> Result:
    now = _now(now)
    if _already_seen(db, inbound.message_id):
        return Result(case=None)
    row = open_case_for(db, owner, inbound.sender)
    if row is None:
        service_id = detect_service(inbound.text) if inbound.text else None
        if inbound.reply_id.startswith('c:svc:') and inbound.reply_id.split(':', 2)[2] in ops.SERVICES:
            service_id = inbound.reply_id.split(':', 2)[2]
        row = _create(db, owner, phone=inbound.sender, service_id=service_id or 'tow', channel='whatsapp',
                      request_key=f'wa:{inbound.message_id}', customer=inbound.name,
                      service_confirmed=service_id is not None)
    data = deepcopy(row.data)
    version = row.version
    _record_inbound(db, owner, row, inbound, 'customer', now)
    outgoing: list[Outgoing] = []
    text = inbound.text

    # 1) Acil — her aşamada önce gelir.
    if (text and is_emergency(text)) or inbound.reply_id == 'c:safe:danger':
        if data['status'] not in {'emergency'}:
            ops.apply(data, _action('emergency', version))
        outgoing.append(_say('customer', 'emergency',
                             '🚨 Yaralanma, yangın ya da yakın tehlike varsa HEMEN 112’yi arayın; bu hat acil '
                             'yardımın yerine geçmez. Talebinizi öncelikli olarak danışmanımıza aktardım.'))
        _commit(db, owner, row, data, version, outgoing, now)
        return Result(ops.public(row), [outgoing[-1].body])

    status = data['status']
    n = normalize_for_intent(text) if text else ''

    # 2) Şablona dokunuldu → pencere açıldı; müşteri konum göndermek istiyor,
    #    önce başka soru sorulmaz.
    if inbound.reply_id == 'c:loc:ready' and data['location'] is None \
            and status in {'intake', 'needs_location', 'ready'}:
        data['intake']['awaiting'] = 'location'
        outgoing.append(_location_request())
        _commit(db, owner, row, data, version, outgoing, now)
        return Result(ops.public(row), [outgoing[-1].body])
    # 3) Sevk sonrası: soru, iptal, insan, serbest not.
    elif status not in {'intake', 'needs_location', 'ready'}:
        if inbound.kind == 'location':
            outgoing.append(_say('customer', 'location_after_dispatch',
                                 'Ekip yönlendirildikten sonra konum değişikliğini danışmanımız ekip ile '
                                 'teyit edecek; sizi arayacağız.'))
            data['audit'].append(dict(action='location_after_dispatch', at=now.isoformat(),
                                      detail='Sevk sonrası yeni konum geldi — danışman teyidi gerekli.'))
        elif any(w in n for w in CANCEL):
            team = data['assigned_team']
            ops.apply(data, _action('cancel', version))
            if data['status'] == 'cancelled':
                outgoing.append(_say('customer', 'cancelled', 'Talebiniz iptal edildi. İhtiyacınız olursa yeniden yazabilirsiniz.'))
                if team:
                    outgoing.append(_say(f"team:{team['id']}", 'offer_cancelled', 'Müşteri talebi iptal etti; bu teklif geçersiz.'))
            else:
                outgoing.append(_say('customer', 'cancel_review', 'Ekip görevi kabul ettiği için iptalinizi danışmanımız '
                                     'ekiple teyit edecek. Görev otomatik iptal edilmedi.'))
        elif any(w in n for w in HUMAN):
            outgoing.append(_say('customer', 'human_note', 'Mesajınızı danışmanımıza ilettim; sizi arayacaklar.'))
            data['audit'].append(dict(action='human_requested', at=now.isoformat(), detail='Müşteri danışman istedi.'))
        elif any(w in n for w in WHERE):
            outgoing.append(_say('customer', 'status', _status_line(data)))
        elif text:
            data['messages'].append(dict(role='customer', text=text, at=now.isoformat()))
            outgoing.append(_say('customer', 'noted', 'Notunuzu aldım ve ekibe/danışmana ilettim. ' + _status_line(data)))
        _commit(db, owner, row, data, version, outgoing, now)
        return Result(ops.public(row), [o.body for o in outgoing if o.audience == 'customer'])
    # 4) Bilgi toplama sırasında iptal / insan.
    elif any(w in n for w in CANCEL):
        ops.apply(data, _action('cancel', version))
        outgoing.append(_say('customer', 'cancelled', 'Talebiniz iptal edildi. İhtiyacınız olursa yeniden yazabilirsiniz.'))
        _commit(db, owner, row, data, version, outgoing, now)
        return Result(ops.public(row), [outgoing[-1].body])
    elif any(w in n for w in HUMAN):
        ops.apply(data, _action('human', version))
        outgoing.append(_say('customer', 'human', 'Danışmanımıza aktardım; sizi bu numaradan arayacaklar.'))
        _commit(db, owner, row, data, version, outgoing, now)
        return Result(ops.public(row), [outgoing[-1].body])
    else:
        if inbound.kind == 'unsupported':
            # Yolda kalan biri çoğu zaman sesli mesaj atar; sessizce yok saymak
            # yerine ne yapabileceğini söyle ve soruyu yinele.
            outgoing.append(_say('customer', 'unsupported', 'Sesli mesaj, fotoğraf ya da dosyayı şu an '
                                 'işleyemiyorum; lütfen kısaca yazın ya da düğmeleri kullanın.'))
        try:
            _absorb_customer(data, inbound, version, outgoing)
        except HTTPException as exc:
            outgoing.append(_say('customer', 'not_applied', 'Bunu şu an işleyemedim; danışmanımız yardımcı olacak.'))
            data['audit'].append(dict(action='rejected', at=now.isoformat(), detail=str(exc.detail)[:200]))

    # 5) Durum ilerlediyse: soru sor ya da ekibe teklif et.
    if data['status'] in {'intake', 'needs_location', 'ready'}:
        question = _next_question(data)
        if question:
            outgoing.append(question)
        elif data['status'] == 'ready' and data['share_permission']:
            outgoing.extend(_auto_offer(db, owner, row, data, version, now))
    _commit(db, owner, row, data, version, outgoing, now)
    return Result(ops.public(row), [o.body for o in outgoing if o.audience == 'customer'])


def _status_line(data: dict) -> str:
    status = data['status']
    team = (data.get('assigned_team') or {}).get('name')
    eta = data.get('eta_minutes')
    if status == 'offered':
        return f'Talebiniz {team} ekibine iletildi, onayını bekliyoruz. Henüz yola çıkmadı.'
    if status == 'accepted':
        return f'{team} görevi kabul etti; tahmini varış yaklaşık {eta} dakika. Yola çıkınca haber vereceğiz.'
    if status == 'en_route':
        return f'{team} yolda; tahmini varış yaklaşık {eta} dakika. Trafikle değişebilir.'
    if status == 'arrived':
        return 'Ekibimiz konumunuza ulaştı.'
    if status == 'transporting':
        return f"Aracınız {data['destination']} adresine taşınıyor."
    return f"Talebinizin durumu: {ops.STATUS_LABELS[status]}."


# ─── Ekibe teklif ────────────────────────────────────────────────────────────


def _busy_teams(db: Session, owner: User, row: AutomotiveCase) -> set[str]:
    return set(db.scalars(select(AutomotiveCase.team_slot).where(
        *ops.scoped(owner), AutomotiveCase.team_slot.is_not(None), AutomotiveCase.id != row.id)).all())


def _auto_offer(db: Session, owner: User, row: AutomotiveCase, data: dict, version: int,
                now: datetime) -> list[Outgoing]:
    """En yakın, uygun, boşta ve daha önce reddetmemiş ekibe teklif eder."""
    busy = _busy_teams(db, owner, row)
    options = [t for t in ops.candidates(data)
               if t['id'] not in busy and t['id'] not in data.get('declined_teams', [])]
    if options:
        team = options[0]
        try:
            ops.apply(data, _action('offer', version, team_id=team['id']))
        except HTTPException as exc:  # ör. konum 30 dakikadan eski
            data['audit'].append(dict(action='offer_blocked', at=now.isoformat(), detail=str(exc.detail)[:200]))
            options = []
    if not options:
        ops.apply(data, _action('human', version))
        return [_say('customer', 'no_team',
                     'Şu an bölgenizde uygun ekip göremiyorum. Talebinizi öncelikli olarak danışmanımıza '
                     'aktardım; sizi hemen arayacaklar. Yakın tehlike varsa 112’yi arayın.',
                     template=('automotive_wa_template_customer_update',
                               ['Bölgenizde uygun ekip bulunamadı, danışmanımız sizi arayacak.'], []))]
    data['offered_at'] = now.isoformat()
    loc, case_id = data['location'], row.id
    hazard = '\n⚠️ Araç yol şeridinde — ÖNCELİKLİ.' if data.get('priority') == 'high' else ''
    body = (f"Yeni iş: {data['service_title']}\nMesafe: {team['distance_km']} km\n"
            f"Araç: {data['vehicle']}\nVarış yeri: {data['destination']}\n"
            f"Konum: {data['handoff']['map_url']}{hazard}")
    buttons = [(f't:accept15:{case_id}', "15 dk'da gelirim"), (f't:accept30:{case_id}', "30 dk'da gelirim"),
               (f't:decline:{case_id}', 'Reddet')]
    return [
        _say(f"team:{team['id']}", 'team_offer', body, buttons=buttons,
             template=('automotive_wa_template_team_offer',
                       [data['service_title'], f"{team['distance_km']} km", data['vehicle'] or '-',
                        data['handoff']['map_url']],
                       [b[0] for b in buttons])),
        _say('customer', 'offered',
             f"Talebinizi size en yakın ekibimize ({team['name']}, yaklaşık {team['distance_km']} km) ilettik. "
             'Ekip onaylayınca tahmini varış süresini size yazacağız.',
             template=('automotive_wa_template_customer_update',
                       [f"Talebiniz en yakın ekibimize ({team['name']}) iletildi, onay bekleniyor."], [])),
    ]


# ─── Ekip yanıtları ──────────────────────────────────────────────────────────

TEAM_ACTIONS = {
    'accept15': ('accept', 15), 'accept30': ('accept', 30), 'decline': ('decline', None),
    'en_route': ('en_route', None), 'arrived': ('arrived', None),
    'transport': ('transport', None), 'complete': ('complete', None),
}


def _after_team_step(data: dict, case_id: str, team_id: str) -> list[Outgoing]:
    status, team = data['status'], data['assigned_team']
    eta = data.get('eta_minutes')
    to_team = f'team:{team_id}'
    if status == 'accepted':
        loc = data['location']
        return [
            _say('customer', 'accepted',
                 f"✅ {team['name']} talebinizi kabul etti. Tahmini varış yaklaşık {eta} dakika. "
                 'Ekip yola çıkınca size haber vereceğiz.',
                 template=('automotive_wa_template_customer_update',
                           [f"{team['name']} kabul etti, tahmini varış {eta} dakika."], [])),
            Outgoing(to_team, 'team_location', f"Müşteri konumu: {data['handoff']['map_url']}",
                     session=wa.location_content(latitude=loc['latitude'], longitude=loc['longitude'],
                                                 name='Yol yardım', address=loc.get('address') or '')),
            _say(to_team, 'team_next', 'Yola çıkınca dokunun.', buttons=[(f't:en_route:{case_id}', 'Yola çıktım')]),
        ]
    if status == 'en_route':
        return [
            _say('customer', 'en_route', f'🚛 Ekibimiz yola çıktı, yaklaşık {eta} dakika içinde yanınızda. '
                 'Lütfen güvenli bir yerde bekleyin.',
                 template=('automotive_wa_template_customer_update', [f'Ekibimiz yola çıktı, yaklaşık {eta} dakika.'], [])),
            _say(to_team, 'team_next', 'Konuma ulaşınca dokunun.', buttons=[(f't:arrived:{case_id}', 'Ulaştım')]),
        ]
    if status == 'arrived':
        tow = _is_tow(data)
        return [
            _say('customer', 'arrived', 'Ekibimiz konumunuza ulaştı.',
                 template=('automotive_wa_template_customer_update', ['Ekibimiz konumunuza ulaştı.'], [])),
            _say(to_team, 'team_next', 'Araç yüklenince dokunun.' if tow else 'İş bitince dokunun.',
                 buttons=[(f't:transport:{case_id}', 'Araç yüklendi')] if tow else [(f't:complete:{case_id}', 'İş tamam')]),
        ]
    if status == 'transporting':
        return [
            _say('customer', 'transporting', f"Aracınız {data['destination']} adresine taşınıyor.",
                 template=('automotive_wa_template_customer_update', [f"Aracınız {data['destination']} adresine taşınıyor."], [])),
            _say(to_team, 'team_next', 'Teslim edince dokunun.', buttons=[(f't:complete:{case_id}', 'Teslim ettim')]),
        ]
    if status == 'completed':
        return [
            _say('customer', 'completed', 'İşlem tamamlandı. Geçmiş olsun, iyi yolculuklar.',
                 template=('automotive_wa_template_customer_update', ['İşleminiz tamamlandı. Geçmiş olsun.'], [])),
            _say(to_team, 'team_done', 'Teşekkürler, iş kapandı.'),
        ]
    return []


def handle_team(db: Session, owner: User, team_id: str, inbound: wa.Inbound, *,
                now: datetime | None = None) -> Result:
    now = _now(now)
    if _already_seen(db, inbound.message_id):
        return Result(case=None)
    parts = inbound.reply_id.split(':')
    row = None
    if len(parts) == 3 and parts[0] == 't' and parts[1] in TEAM_ACTIONS:
        row = db.scalar(select(AutomotiveCase).where(AutomotiveCase.id == parts[2], *ops.scoped(owner)))
    if row is None:
        logger.info('automotive.team_reply.ignored', extra={'team_id': team_id})
        return Result(case=None)
    data, version = deepcopy(row.data), row.version
    _record_inbound(db, owner, row, inbound, f'team:{team_id}', now)
    outgoing: list[Outgoing] = []

    if not data.get('assigned_team') or data['assigned_team']['id'] != team_id:
        outgoing.append(_say(f'team:{team_id}', 'not_assigned', 'Bu iş size atanmış değil ya da başka ekibe geçti.'))
    else:
        kind, eta = TEAM_ACTIONS[parts[1]]
        try:
            ops.apply(data, _action(kind, version, eta_minutes=eta))
        except HTTPException:
            outgoing.append(_say(f'team:{team_id}', 'step_rejected', 'Bu adım işin şu anki durumunda uygulanamaz.'))
        else:
            if kind == 'decline':
                data.setdefault('declined_teams', []).append(team_id)
                outgoing.extend(_auto_offer(db, owner, row, data, version, now))
            else:
                outgoing.extend(_after_team_step(data, row.id, team_id))
    _commit(db, owner, row, data, version, outgoing, now)
    return Result(ops.public(row), [])


# ─── Zaman aşımı ve teslim hatası ────────────────────────────────────────────


def expire_offer(db: Session, owner: User, row: AutomotiveCase, *, reason: str,
                 now: datetime | None = None) -> bool:
    """Bekleyen teklifi düşürür ve sıradakine geçer. Teklif zaten kabul/ret
    edildiyse hiçbir şey yapmaz (yarış güvenli: durum yeniden okunur)."""
    now = _now(now)
    db.refresh(row)
    data, version = deepcopy(row.data), row.version
    if data['status'] != 'offered' or not data.get('assigned_team'):
        return False
    team_id = data['assigned_team']['id']
    ops.apply(data, _action('decline', version))
    data.setdefault('declined_teams', []).append(team_id)
    data['audit'].append(dict(action='offer_expired', at=now.isoformat(), detail=f'{team_id}: {reason}'))
    outgoing = [_say(f'team:{team_id}', 'offer_withdrawn', 'Teklif süresi doldu; iş başka ekibe yönlendirildi.')]
    outgoing += _auto_offer(db, owner, row, data, version, now)
    _commit(db, owner, row, data, version, outgoing, now)
    return True


def sweep_expired_offers(db: Session, *, now: datetime | None = None, owner: User | None = None) -> int:
    """Süresi dolan teklifleri düşürür. Outbox worker her turda çağırır;
    `owner` verilirse yalnız o hesabın işlerine bakar (demo düğmesi)."""
    now = _now(now)
    count = 0
    query = select(AutomotiveCase).where(AutomotiveCase.team_slot.is_not(None))
    if owner is not None:
        query = query.where(*ops.scoped(owner))
    for row in db.scalars(query).all():
        offered_at = row.data.get('offered_at')
        if row.data['status'] != 'offered' or not offered_at:
            continue
        if now - _aware(datetime.fromisoformat(offered_at)) >= OFFER_TIMEOUT:
            owner = db.get(User, row.owner_id)
            if owner and expire_offer(db, owner, row, reason='zaman aşımı', now=now):
                count += 1
    return count


def handle_failures(db: Session, message_ids: list[str], *, now: datetime | None = None) -> None:
    """Teslim edilemeyen mesajın işe etkisi. Yalnız etkisi olan iki durum var:
    ekibe teklif gitmediyse sıradakine geç; müşteriye konum isteği gitmediyse
    danışmana düşür (WhatsApp'ı olmayan sabit hat vb.)."""
    for message_id in message_ids:
        message = db.get(AutomotiveMessage, message_id)
        if message is None:
            continue
        row = db.get(AutomotiveCase, message.case_id)
        owner = db.get(User, message.owner_id)
        if row is None or owner is None:
            continue
        if message.purpose == 'team_offer':
            expire_offer(db, owner, row, reason=f'teklif iletilemedi ({message.delivery_status})', now=now)
        elif message.purpose == 'location_request' and row.data['status'] in {'intake', 'needs_location'}:
            db.refresh(row)
            data, version = deepcopy(row.data), row.version
            ops.apply(data, _action('human', version))
            data['audit'].append(dict(action='whatsapp_unreachable', at=_now(now).isoformat(),
                                      detail='Konum isteği iletilemedi — danışman arayıp konumu almalı.'))
            _commit(db, owner, row, data, version, [], _now(now))


def apply_status(db: Session, update: wa.StatusUpdate, *, now: datetime | None = None) -> None:
    """Sağlayıcı teslim bildirimi. Sıra dışı gelebilir (okundu, iletildi'den
    önce) — durum yalnız ileri gider."""
    order = {'queued': 0, 'accepted': 1, 'sent': 2, 'delivered': 3, 'read': 4}
    message = db.scalar(select(AutomotiveMessage).where(
        AutomotiveMessage.provider_message_id == update.provider_message_id))
    if message is None or message.direction != 'out':
        return
    if update.status == 'failed':
        if message.delivery_status == 'failed':
            return
        message.delivery_status, message.error = 'failed', update.error or 'Sağlayıcı teslim edemedi'
        message.updated_at = _now(now)
        db.commit()
        handle_failures(db, [message.id], now=now)
    elif order.get(update.status, -1) > order.get(message.delivery_status, -1):
        message.delivery_status, message.updated_at = update.status, _now(now)
        db.commit()


def make_delivery_handler(session_factory):
    """Outbox handler: kuyruktaki mesajı Meta'ya gönderir.

    Ağ/5xx hatası yükselir → outbox tekrar dener. Kalıcı ret (4xx) tekrar
    denenmez: mesaj `failed` olur ve işe etkisi uygulanır.
    """
    def deliver(event) -> None:
        message_id = (event.payload_json or {}).get('message_id')
        with session_factory() as db:
            message = db.get(AutomotiveMessage, message_id)
            if message is None or message.delivery_status != 'queued':
                return
            payload = message.payload or {}
            try:
                provider_id = wa.send(wa.envelope(payload.get('to') or '', payload['content']))
            except (wa.PermanentSendError, ValueError) as exc:
                message.delivery_status, message.error = 'failed', str(exc)[:300]
                message.updated_at = _now()
                db.commit()
                handle_failures(db, [message.id])
                return
            message.provider_message_id, message.delivery_status = provider_id, 'accepted'
            message.updated_at = _now()
            db.commit()
    return deliver


# ─── Telefon ─────────────────────────────────────────────────────────────────


@dataclass
class CallOutcome:
    say: str
    transfer: bool
    ask_again: bool = False
    case: dict | None = None


def handle_call(db: Session, owner: User, *, call_sid: str, caller: str, speech: str,
                attempt: int = 1, now: datetime | None = None) -> CallOutcome:
    """Arayanın ilk cümlesinden iş açar ve WhatsApp'tan konum ister.

    Arayana söylenen cümle GERÇEĞE bağlıdır: WhatsApp gönderimi kapalıysa ya da
    şablon yoksa "size mesaj gönderdik" DENMEZ.
    """
    now = _now(now)
    settings = get_settings()
    emergency = is_emergency(speech)
    service_id = detect_service(speech)
    if not emergency and service_id is None and attempt < 2:
        return CallOutcome('Aracınızda ne oldu? Çekici, akü, lastik, yakıt ya da kaza gibi kısaca söyleyin.',
                           transfer=False, ask_again=True)
    service_id = service_id or 'tow'
    phone = caller if wa.E164.fullmatch(caller or '') else None
    row = _create(db, owner, phone=phone, service_id=service_id, channel='phone',
                  request_key=f'call:{call_sid}', customer='Arayan', service_confirmed=True)
    data, version = deepcopy(row.data), row.version
    if data['intake'].get('call_processed'):  # aynı çağrının tekrar eden webhook'u
        return CallOutcome('Sizi görevlimize bağlıyorum.', transfer=True, case=ops.public(row))
    data['intake']['call_processed'] = True
    data['messages'].append(dict(role='customer', text=speech[:1200], at=now.isoformat(), channel='phone'))
    outgoing: list[Outgoing] = []
    if emergency:
        ops.apply(data, _action('emergency', version))
        _commit(db, owner, row, data, version, outgoing, now)
        return CallOutcome('Yaralanma, yangın ya da yakın tehlike varsa hemen 112’yi arayın; bu hat acil '
                           'yardımın yerine geçmez. Şimdi sizi görevlimize bağlıyorum.', transfer=True,
                           case=ops.public(row))

    title = ops.SERVICES[service_id]['title'].lower()
    mobile = ops.SERVICES[service_id]['mobile']
    if phone and mobile:
        body = (f'{settings.automotive_brand}: {title} talebiniz için kaydınızı açtık. En yakın ekibi '
                'yönlendirebilmemiz için bu mesaja dokunup konumunuzu paylaşın.')
        outgoing.append(Outgoing('customer', 'location_request', body,
                                 session=wa.location_request_content(body),
                                 template=('automotive_wa_template_customer_location', [title], ['c:loc:ready'])))
    messages = _commit(db, owner, row, data, version, outgoing, now)
    if any(m.delivery_status == 'queued' for m in messages):
        say = ('Kaydınızı açtım. Az önce WhatsApp’tan size bir mesaj gönderdik; konumunuzu paylaştığınız anda '
               'size en yakın ekibimizi yönlendireceğiz. Şimdi sizi görevlimize bağlıyorum.')
    else:
        say = 'Kaydınızı açtım. Şimdi sizi görevlimize bağlıyorum; konumunuzu ve ihtiyacınızı teyit edecek.'
    return CallOutcome(say, transfer=True, case=ops.public(row))


def case_messages(db: Session, owner: User, case_id: str) -> list[dict]:
    ops.fetch(db, owner, case_id)  # sahiplik kontrolü
    rows = db.scalars(select(AutomotiveMessage).where(AutomotiveMessage.case_id == case_id)
                      .order_by(AutomotiveMessage.created_at, AutomotiveMessage.id)).all()
    return [dict(id=m.id, direction=m.direction, audience=m.audience, purpose=m.purpose, form=m.form,
                 body=m.body, delivery_status=m.delivery_status, error=m.error,
                 buttons=(m.payload or {}).get('buttons') or [],
                 location_request=bool((m.payload or {}).get('location_request')),
                 at=_aware(m.created_at).isoformat()) for m in rows]
