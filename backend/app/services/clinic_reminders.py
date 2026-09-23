"""Randevu hatırlatma + düğmeli teyit (K.B).

Kliniğin en çok para kaybettiği yer gelmeyen hastadır; boş kalan koltuk geri
gelmez. Bu modül randevudan 24 saat ve 2 saat önce hastaya hatırlatma gönderir
ve **[Geleceğim] [İptal] [Ertele]** yanıtını işler:

- Geleceğim → hastanın KATILIM teyidi kaydedilir. Randevunun klinik onayı
              (hekim ataması, takvim kontrolü) ayrı bir karardır; hastanın
              düğmesi onu atlatmaz.
- İptal     → randevu iptal edilir ve takvim slotu SERBEST BIRAKILIR: saat
              başka hastaya önerilebilir hâle gelir (asıl değer budur).
- Ertele    → mevcut randevu KORUNUR, ekip yeni saat için döner. Yeni saat
              bulunmadan randevuyu iptal etmek hastayı randevusuz bırakırdı.

Planlama randevunun hangi kanaldan oluştuğuna bakmaz (telefon, web, operatör):
worker her turda yaklaşan randevuları tarar. Ama yalnız HASTAYLA KARARLAŞTIRILMIŞ
randevuya hatırlatma gider — yapay zekânın hekim ekranı için hazırladığı taslak
da PENDING durumdadır ve saati varsa bile hasta o saati hiç kabul etmemiştir. Randevu saati
değişirse planlı hatırlatmalar yenilenir, iptal edilirse silinir.

Kanal: hastanın WhatsApp konuşması varsa WhatsApp (24 saat penceresi kapalıysa
onaylı şablon); yoksa ya da WhatsApp teslim edilemeyeceği belliyse SMS.

Bilinçli olarak YAPILMAYAN: gelmeme risk modeli (`learning/noshow`) sentetik
veriyle eğitildi; gerçek hastaya kimin mesaj alacağına onunla karar verilmez.
Hatırlatma herkese gider.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.text_understanding import normalize_for_intent
from app.core.config import get_settings
from app.models import (
    Clinic,
    ClinicChannel,
    ClinicConversation,
    ClinicConversationStatus,
    ClinicMessage,
    ClinicMessageSender,
    ClinicPatient,
    ClinicalAppointment,
    ClinicalAppointmentStatus,
    Reminder,
    ReminderStatus,
)
from app.services import clinic_whatsapp
from app.services.notification_service import _format_dt_tr
from app.services.sms_service import get_sms_provider

logger = logging.getLogger('cognivault.clinic.reminders')

OFFSETS = (('24h', timedelta(hours=24)), ('2h', timedelta(hours=2)))
HORIZON = timedelta(hours=26)          # bu kadar ileriye bakarak planla
REPLY_WINDOW = timedelta(hours=30)     # hatırlatmadan sonra yazılı yanıt bu süre tanınır
ACTIVE = (ClinicalAppointmentStatus.PENDING, ClinicalAppointmentStatus.CONFIRMED)
ACTIONS = ('confirm', 'cancel', 'reschedule')
BUTTONS = {'confirm': 'Geleceğim', 'cancel': 'İptal', 'reschedule': 'Ertele'}
# Yalnız KISA ve net yazılı yanıtlar hatırlatma yanıtı sayılır; uzun mesaj
# ("iptal edersem ücret alınır mı?") normal akışa (yapay zekâ + hekim) gider.
TEXT_REPLIES = {
    'confirm': ('gelecegim', 'gelicem', 'geliyorum', 'onayliyorum', 'evet gelecegim'),
    'cancel': ('iptal', 'iptal edin', 'gelemeyecegim', 'gelemiyorum', 'gelemem'),
    'reschedule': ('ertele', 'erteleyin', 'baska gun', 'baska saat', 'saati degistir'),
}
MAX_TEXT_REPLY_WORDS = 3


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _now(now: datetime | None) -> datetime:
    return now or datetime.now(timezone.utc)


def patient_agreed(appointment: ClinicalAppointment) -> bool:
    """Hastayla kararlaştırılmış mı? Klinik onaylıysa evet; PENDING ise yalnız
    hasta kendisi seçtiyse (telefon/web akışı `confirmed_via` yazar) ya da
    operatör hastayla konuşup açtıysa. Yapay zekâ taslağı değil."""
    if appointment.status == ClinicalAppointmentStatus.CONFIRMED:
        return True
    meta = appointment.metadata_json or {}
    return appointment.status == ClinicalAppointmentStatus.PENDING and bool(
        meta.get('confirmed_via') or meta.get('created_by') == 'operator_panel')


# ─── Planlama ────────────────────────────────────────────────────────────────


def plan(db: Session, *, now: datetime | None = None) -> int:
    """Yaklaşan randevular için hatırlatma satırlarını hizalar; eklenen sayısını döner.

    Geçmişe düşen hatırlatma planlanmaz (randevu 3 saat sonraysa 24 saatlik
    atlanır). Saati değişen randevunun eski planlı hatırlatmaları silinir;
    gönderilmişler denetim izi için kalır.
    """
    now = _now(now)
    added = 0
    appointments = db.scalars(select(ClinicalAppointment).where(
        ClinicalAppointment.status.in_(ACTIVE),
        ClinicalAppointment.starts_at.is_not(None),
    )).all()
    for appointment in appointments:
        starts = _aware(appointment.starts_at)
        if not (now < starts <= now + HORIZON) or not patient_agreed(appointment):
            continue
        expected = {starts - offset for _, offset in OFFSETS if starts - offset > now}
        existing = db.scalars(select(Reminder).where(Reminder.appointment_id == appointment.id)).all()
        for reminder in existing:
            if reminder.status == ReminderStatus.SCHEDULED and _aware(reminder.scheduled_for) not in expected:
                db.delete(reminder)
        known = {_aware(r.scheduled_for) for r in existing}
        for when in sorted(expected - known):
            db.add(Reminder(clinic_id=appointment.clinic_id, appointment_id=appointment.id,
                            channel=ClinicChannel.WHATSAPP, scheduled_for=when, status=ReminderStatus.SCHEDULED))
            added += 1
    # İptal edilmiş ya da geçmiş randevuların planlı hatırlatmaları gitmesin.
    for reminder in db.scalars(select(Reminder).where(Reminder.status == ReminderStatus.SCHEDULED)).all():
        appointment = db.get(ClinicalAppointment, reminder.appointment_id)
        if appointment is None or not patient_agreed(appointment) or _aware(appointment.starts_at) <= now:
            db.delete(reminder)
    db.commit()
    return added


# ─── Gönderim ────────────────────────────────────────────────────────────────


def _whatsapp_conversation(db: Session, clinic_id: int, patient_id: int) -> ClinicConversation | None:
    """Hastanın, gönderim rotası bilinen (gerçek webhook'tan gelmiş) WhatsApp konuşması."""
    rows = db.scalars(select(ClinicConversation).where(
        ClinicConversation.clinic_id == clinic_id,
        ClinicConversation.patient_id == patient_id,
        ClinicConversation.channel == ClinicChannel.WHATSAPP,
    ).order_by(ClinicConversation.updated_at.desc(), ClinicConversation.id.desc())).all()
    return next((c for c in rows if clinic_whatsapp.conversation_delivers(c)), None)


def _first_name(patient: ClinicPatient) -> str:
    """Gerçek ad; yoksa boş. Sistemin koyduğu yer tutucular ("WhatsApp Hasta")
    hastaya ad gibi söylenmez."""
    full = (patient.full_name or '').strip()
    return '' if not full or 'hasta' in full.lower() else full.split(' ')[0]


def reminder_text(appointment: ClinicalAppointment, clinic: Clinic, patient: ClinicPatient, *, soon: bool) -> str:
    name = _first_name(patient)
    greeting = f'Merhaba {name}, ' if name else 'Merhaba, '
    when = _format_dt_tr(appointment.starts_at)
    doctor = (appointment.metadata_json or {}).get('physician_name')
    detail = f'{appointment.department}' + (f', {doctor}' if doctor else '')
    lead = 'randevunuza 2 saat kaldı' if soon else 'yarınki randevunuzu hatırlatırız'
    return f'{greeting}{clinic.name} {lead}: {when} ({detail}). Gelebilecek misiniz?'


def _sms_text(body: str) -> str:
    return body.replace('Gelebilecek misiniz?', 'İptal ya da değişiklik için kliniğimizi arayın.')


def send_due(db: Session, *, now: datetime | None = None) -> int:
    """Vakti gelen hatırlatmaları gönderir; gönderilen sayısını döner."""
    now = _now(now)
    due = db.scalars(select(Reminder).where(
        Reminder.status == ReminderStatus.SCHEDULED, Reminder.scheduled_for <= now,
    ).order_by(Reminder.scheduled_for)).all()
    sent = 0
    by_appointment: dict[int, list[Reminder]] = {}
    for reminder in due:
        by_appointment.setdefault(reminder.appointment_id, []).append(reminder)
    for appointment_id, reminders in by_appointment.items():
        # Worker bir süre durduysa aynı randevunun iki hatırlatması birden
        # vadesi gelmiş olabilir: hastaya ikisi birden gitmez, yalnız en yenisi.
        *stale, reminder = sorted(reminders, key=lambda r: _aware(r.scheduled_for))
        for old in stale:
            db.delete(old)
        appointment = db.get(ClinicalAppointment, appointment_id)
        if appointment is None or not patient_agreed(appointment) or _aware(appointment.starts_at) <= now:
            db.delete(reminder)
            continue
        if _deliver(db, reminder, appointment, now=now):
            sent += 1
    db.commit()
    return sent


def _deliver(db: Session, reminder: Reminder, appointment: ClinicalAppointment, *, now: datetime) -> bool:
    clinic = db.get(Clinic, appointment.clinic_id)
    patient = db.get(ClinicPatient, appointment.patient_id)
    soon = _aware(appointment.starts_at) - _aware(reminder.scheduled_for) < timedelta(hours=12)
    body = reminder_text(appointment, clinic, patient, soon=soon)
    reminder.attempts += 1

    conversation = _whatsapp_conversation(db, clinic.id, patient.id)
    if conversation is not None:
        ids = [f'r:{action}:{appointment.id}' for action in ACTIONS]
        message = ClinicMessage(
            clinic_id=clinic.id, conversation_id=conversation.id, sender=ClinicMessageSender.SYSTEM,
            content=body, language=patient.language, intent=None,
            metadata_json={
                'reminder_id': reminder.id, 'appointment_id': appointment.id,
                'delivery': clinic_whatsapp.PENDING, 'escalate_on_failure': False,
                'buttons': [[i, BUTTONS[a]] for i, a in zip(ids, ACTIONS)],
                'template': {'kind': 'reminder', 'quick_replies': ids,
                             'params': [_first_name(patient) or 'değerli hastamız',
                                        clinic.name, _format_dt_tr(appointment.starts_at)]},
            })
        db.add(message)
        db.flush()
        clinic_whatsapp.flush(db, conversation, now=now)
        db.refresh(message)
        status = (message.metadata_json or {}).get('delivery')
        if status not in clinic_whatsapp.UNDELIVERABLE:
            reminder.status, reminder.channel, reminder.last_error = ReminderStatus.SENT, ClinicChannel.WHATSAPP, None
            db.add(reminder)
            return True
        logger.info('clinic.reminder.whatsapp_unavailable', extra={'reminder_id': reminder.id, 'status': status})

    # Yedek: SMS (WhatsApp konuşması yok ya da şablon/numara yüzünden gidemez).
    result = get_sms_provider().send(to=patient.phone, body=_sms_text(body))
    if result.ok:
        # Ayrı bir SMS kanal değeri yok; telefon numarasına gittiği için PHONE.
        reminder.status, reminder.channel, reminder.last_error = ReminderStatus.SENT, ClinicChannel.PHONE, None
    else:
        reminder.status, reminder.last_error = ReminderStatus.FAILED, (result.error or 'SMS gönderilemedi')[:500]
    db.add(reminder)
    return result.ok


# ─── Hasta yanıtı ────────────────────────────────────────────────────────────


def _button_action(raw: dict | None) -> tuple[str | None, int | None]:
    """Sağlayıcı düğme yükünden (eylem, randevu kimliği). Twilio'da içerik
    şablonu düğme kimlikleri sabittir ("r:confirm"), Meta'da randevuya özgüdür."""
    raw = raw or {}
    payload = (raw.get('ButtonPayload')
               or (raw.get('button') or {}).get('payload')
               or ((raw.get('interactive') or {}).get('button_reply') or {}).get('id') or '')
    parts = str(payload).split(':')
    if len(parts) < 2 or parts[0] != 'r' or parts[1] not in ACTIONS:
        return None, None
    appointment_id = int(parts[2]) if len(parts) == 3 and parts[2].isdigit() else None
    return parts[1], appointment_id


def _text_action(body: str) -> str | None:
    n = normalize_for_intent(body).rstrip('.! ')
    if not n or len(n.split()) > MAX_TEXT_REPLY_WORDS:
        return None
    return next((action for action, phrases in TEXT_REPLIES.items() if n in phrases), None)


def _reminded_appointment(db: Session, clinic_id: int, patient_id: int, now: datetime,
                          appointment_id: int | None) -> ClinicalAppointment | None:
    """Yanıtın ait olduğu randevu: düğmede kimlik varsa o (ama YALNIZ bu hastanın
    ve bu kliniğin ise); yoksa hastanın son hatırlatılan, hâlâ yaklaşan randevusu."""
    if appointment_id is not None:
        appointment = db.get(ClinicalAppointment, appointment_id)
        if appointment and appointment.clinic_id == clinic_id and appointment.patient_id == patient_id:
            return appointment
        return None
    candidates = db.scalars(select(ClinicalAppointment).where(
        ClinicalAppointment.clinic_id == clinic_id, ClinicalAppointment.patient_id == patient_id,
        ClinicalAppointment.status.in_(ACTIVE))).all()
    reminded = []
    for appointment in candidates:
        if _aware(appointment.starts_at) is None or _aware(appointment.starts_at) <= now:
            continue
        last = max((_aware(r.scheduled_for) for r in db.scalars(select(Reminder).where(
            Reminder.appointment_id == appointment.id, Reminder.status == ReminderStatus.SENT)).all()),
            default=None)
        if last is not None and now - last <= REPLY_WINDOW:
            reminded.append((last, appointment))
    return max(reminded, key=lambda pair: pair[0])[1] if reminded else None


def handle_reply(db: Session, clinic: Clinic, incoming, *, now: datetime | None = None):
    """Gelen WhatsApp mesajı bir hatırlatma yanıtıysa işler ve sonucu döner;
    değilse None (mesaj normal akışa — yapay zekâ + hekim — gider).

    Yapay zekâ bu yanıtlarda çalışmaz: "İptal" düğmesine basan hastaya iki ayrı
    cevap (biri modelden) gitmesin.
    """
    from app.services.clinical_appointment_service import set_clinical_appointment_status
    from app.services.clinical_service import IngestionResult

    now = _now(now)
    action, appointment_id = _button_action(incoming.raw_payload)
    if action is None:
        action = _text_action(incoming.body or '')
    if action is None:
        return None
    patient = db.scalar(select(ClinicPatient).where(ClinicPatient.clinic_id == clinic.id,
                                                    ClinicPatient.phone == incoming.from_phone))
    if patient is None:
        return None
    appointment = _reminded_appointment(db, clinic.id, patient.id, now, appointment_id)
    conversation = _whatsapp_conversation(db, clinic.id, patient.id)
    if appointment is None or conversation is None:
        return None
    if incoming.external_message_id:
        # Sağlayıcı aynı yanıtı tekrar gönderdiyse ikinci kez işlenmez.
        seen = db.scalar(select(ClinicMessage).where(
            ClinicMessage.external_message_id == incoming.external_message_id))
        if seen is not None:
            return IngestionResult(clinic=clinic, patient=patient, conversation=conversation, message=seen,
                                   action='duplicate_ignored')

    patient_message = ClinicMessage(
        clinic_id=clinic.id, conversation_id=conversation.id, sender=ClinicMessageSender.PATIENT,
        content=incoming.body or BUTTONS[action], language=patient.language,
        external_message_id=incoming.external_message_id,
        metadata_json={'reminder_reply': action, 'appointment_id': appointment.id}, created_at=now)
    db.add(patient_message)
    db.flush()

    when = _format_dt_tr(appointment.starts_at)
    if action == 'confirm':
        # Katılım teyidi — randevunun klinik onay durumuna dokunulmaz.
        reply = f'Teşekkürler, {when} için sizi bekliyoruz. Görüşmek üzere.'
    elif action == 'cancel':
        # Slot da burada serbest kalır (set_clinical_appointment_status).
        set_clinical_appointment_status(db, clinic, appointment.id, ClinicalAppointmentStatus.CANCELLED.value)
        reply = f'{when} randevunuz iptal edildi. Yeni randevu için buradan yazabilirsiniz.'
    else:
        # Randevu korunur: yeni saat bulunmadan iptal etmek hastayı randevusuz bırakır.
        conversation.status = ClinicConversationStatus.WAITING_HUMAN
        conversation.metadata_json = {**(conversation.metadata_json or {}),
                                      'reschedule_requested': appointment.id}
        reply = ('Tabii. Ekibimiz size uygun yeni bir saat için buradan dönecek; '
                 f'o zamana kadar {when} randevunuz korunuyor.')

    appointment.metadata_json = {**(appointment.metadata_json or {}),
                                 'reminder_response': {'action': action, 'at': now.isoformat()},
                                 **({'patient_attendance': 'confirmed'} if action == 'confirm' else {})}
    db.add_all([appointment, conversation, ClinicMessage(
        clinic_id=clinic.id, conversation_id=conversation.id, sender=ClinicMessageSender.SYSTEM,
        content=reply, language=patient.language,
        metadata_json={'reminder_reply_ack': action, 'delivery': clinic_whatsapp.PENDING})])
    db.commit()
    db.refresh(conversation)
    return IngestionResult(clinic=clinic, patient=patient, conversation=conversation,
                           message=patient_message, action=f'reminder_{action}', reply=reply)


def run(db: Session, *, now: datetime | None = None) -> dict:
    """Worker tek turu: planla + vakti gelenleri gönder. Ayar kapalıysa hiçbir şey yapmaz."""
    if not get_settings().clinic_reminders_enabled:
        return {'planned': 0, 'sent': 0}
    return {'planned': plan(db, now=now), 'sent': send_due(db, now=now)}
