"""Randevu hatırlatma + [Geleceğim] [İptal] [Ertele] (K.B).

Korunan değişmezler:
- Hatırlatma randevunun nereden oluştuğuna bakmadan planlanır; saat değişince
  yenilenir, iptal edilince silinir, geçmişe düşen planlanmaz.
- Hastaya aynı randevu için iki hatırlatma birden gitmez.
- WhatsApp gidemezse (şablon yok, konuşma yok) SMS'e düşer; hatırlatma
  başarısızlığı hekim kutusunu doldurmaz.
- Yalnız hastayla kararlaştırılmış randevuya gider; yapay zekâ taslağına gitmez.
- "Geleceğim" katılım teyididir; kliniğin onay kuralını (hekim ataması) atlatmaz.
- İptal slotu serbest bırakır; Ertele randevuyu KORUR.
- Düğme yanıtında yapay zekâ çalışmaz (hastaya iki cevap gitmez).
- Başka hastanın randevu kimliğini taşıyan düğme yükü işlenmez.
- Uzun/serbest mesaj ("iptal edersem ücret alınır mı?") randevuyu iptal etmez.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.models import (
    ClinicConversation,
    ClinicConversationStatus,
    ClinicDoctor,
    ClinicDoctorSlot,
    ClinicMessage,
    ClinicMessageSender,
    ClinicPatient,
    ClinicalAppointment,
    ClinicalAppointmentStatus,
    Reminder,
    ReminderStatus,
)
from app.services import clinic_reminders as cr
from app.services.clinical_appointment_service import set_clinical_appointment_status
from app.services.clinical_service import ensure_default_clinic, parse_meta_payload

PHONE = '+905551110001'
OTHER = '+905551110002'
BUSINESS = 'whatsapp:+902120000000'
NOW = datetime(2026, 9, 24, 9, 0, tzinfo=timezone.utc)
_sid = iter(range(1, 10_000))


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(get_settings(), 'clinic_reminders_enabled', True)


@pytest.fixture
def live(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, 'clinic_whatsapp_send_enabled', True)
    monkeypatch.setattr(s, 'twilio_account_sid', 'AC-test')
    monkeypatch.setattr(s, 'twilio_auth_token', 'test-only')
    return s


def whatsapp(client, body, *, phone=PHONE, extra=None):
    """Hasta WhatsApp'tan yazar (gerçek webhook yolu → rota saklanır)."""
    data = {'From': f'whatsapp:{phone}', 'To': BUSINESS, 'Body': body, 'MessageSid': f'SMR{next(_sid)}'}
    return client.post('/api/webhooks/whatsapp', data=data | (extra or {}),
                       headers={'Content-Type': 'application/x-www-form-urlencoded'}).json()


def patient_with_whatsapp(client, db, phone=PHONE):
    data = whatsapp(client, 'Merhaba', phone=phone)
    return db.get(ClinicPatient, data['patient_id'])


def appointment(db, patient, *, hours, slot=False, status=ClinicalAppointmentStatus.PENDING,
                metadata=None):
    clinic = ensure_default_clinic(db)
    slot_id = None
    if slot:
        doctor = ClinicDoctor(clinic_id=clinic.id, full_name='Hatırlatma Test', email=f'r{next(_sid)}@test.local',
                              specialty='Diş Hekimliği', title='Dr.', is_active=True)
        db.add(doctor)
        db.flush()
        row = ClinicDoctorSlot(clinic_id=clinic.id, doctor_id=doctor.id, start_time=NOW + timedelta(hours=hours),
                               end_time=NOW + timedelta(hours=hours, minutes=30), is_booked=True)
        db.add(row)
        db.flush()
        slot_id = row.id
    appt = ClinicalAppointment(clinic_id=clinic.id, patient_id=patient.id, department='Genel Diş Hekimliği',
                               starts_at=NOW + timedelta(hours=hours), status=status, slot_id=slot_id,
                               metadata_json={'confirmed_via': 'web_chat'} if metadata is None else metadata)
    db.add(appt)
    db.commit()
    return appt


def reminders(db, appt):
    return db.scalars(select(Reminder).where(Reminder.appointment_id == appt.id).order_by(Reminder.scheduled_for)).all()


def reminder_messages(db, patient):
    return [m for m in db.scalars(select(ClinicMessage).where(ClinicMessage.sender == ClinicMessageSender.SYSTEM)
                                  .order_by(ClinicMessage.id)).all()
            if (m.metadata_json or {}).get('reminder_id') and m.conversation.patient_id == patient.id]


def age_patient_messages(db, patient, hours=25):
    """24 saat penceresini kapat: hastanın son mesajı eskidi."""
    for m in db.scalars(select(ClinicMessage).where(ClinicMessage.sender == ClinicMessageSender.PATIENT)).all():
        if m.conversation.patient_id == patient.id:
            m.created_at = NOW - timedelta(hours=hours)
    db.commit()


def send(db, at):
    """Worker birkaç saniyede bir planlar: plan başlangıçta, gönderim `at` anında."""
    cr.plan(db, now=NOW)
    return cr.send_due(db, now=at)


# ─── Planlama ────────────────────────────────────────────────────────────────


def test_plans_24h_and_2h(client, db_session):
    appt = appointment(db_session, patient_with_whatsapp(client, db_session), hours=25)
    assert cr.plan(db_session, now=NOW) == 2
    assert [r.scheduled_for.replace(tzinfo=timezone.utc) for r in reminders(db_session, appt)] == [
        NOW + timedelta(hours=1), NOW + timedelta(hours=23)]
    assert cr.plan(db_session, now=NOW) == 0  # idempotent


def test_skips_reminders_already_in_the_past(client, db_session):
    appt = appointment(db_session, patient_with_whatsapp(client, db_session), hours=3)
    cr.plan(db_session, now=NOW)
    assert len(reminders(db_session, appt)) == 1  # yalnız 2 saatlik


def test_rescheduled_appointment_replans(client, db_session):
    appt = appointment(db_session, patient_with_whatsapp(client, db_session), hours=25)
    cr.plan(db_session, now=NOW)
    appt.starts_at = NOW + timedelta(hours=20)
    db_session.commit()
    cr.plan(db_session, now=NOW)
    assert [r.scheduled_for.replace(tzinfo=timezone.utc) for r in reminders(db_session, appt)] == [
        NOW + timedelta(hours=18)]  # 24 saatlik geçmişe düştü, eskiler silindi


def test_ai_draft_is_never_reminded(client, db_session):
    """Yapay zekâ taslağı PENDING'dir ve saati olabilir; hasta o saati kabul etmedi."""
    appt = appointment(db_session, patient_with_whatsapp(client, db_session), hours=25,
                       metadata={'created_from': 'ai_conversation_draft'})
    cr.plan(db_session, now=NOW)
    assert reminders(db_session, appt) == []


def test_operator_created_and_clinic_confirmed_are_reminded(client, db_session):
    patient = patient_with_whatsapp(client, db_session)
    manual = appointment(db_session, patient, hours=25, metadata={'created_by': 'operator_panel'})
    confirmed = appointment(db_session, patient, hours=26, metadata={}, status=ClinicalAppointmentStatus.CONFIRMED)
    cr.plan(db_session, now=NOW)
    assert reminders(db_session, manual) and reminders(db_session, confirmed)


def test_cancelled_appointment_reminders_are_dropped(client, db_session):
    appt = appointment(db_session, patient_with_whatsapp(client, db_session), hours=25)
    cr.plan(db_session, now=NOW)
    appt.status = ClinicalAppointmentStatus.CANCELLED
    db_session.commit()
    cr.plan(db_session, now=NOW)
    assert reminders(db_session, appt) == []


# ─── Gönderim ────────────────────────────────────────────────────────────────


def test_due_reminder_goes_to_whatsapp_with_buttons(client, db_session):
    patient = patient_with_whatsapp(client, db_session)
    appt = appointment(db_session, patient, hours=25)
    assert send(db_session, NOW + timedelta(hours=1, minutes=1)) == 1
    message = reminder_messages(db_session, patient)[-1]
    assert 'yarınki randevunuzu' in message.content
    assert [b[0] for b in message.metadata_json['buttons']] == [
        f'r:confirm:{appt.id}', f'r:cancel:{appt.id}', f'r:reschedule:{appt.id}']
    assert message.metadata_json['delivery'] == 'demo_only'  # gönderim kapalı
    assert reminders(db_session, appt)[0].status == ReminderStatus.SENT


def test_only_latest_reminder_sent_after_worker_downtime(client, db_session):
    patient = patient_with_whatsapp(client, db_session)
    appt = appointment(db_session, patient, hours=25)
    cr.plan(db_session, now=NOW)
    assert cr.send_due(db_session, now=NOW + timedelta(hours=23, minutes=5)) == 1
    assert len(reminder_messages(db_session, patient)) == 1
    assert 'randevunuza 2 saat kaldı' in reminder_messages(db_session, patient)[0].content
    assert len(reminders(db_session, appt)) == 1


def test_closed_window_with_template_queues_template(client, db_session, live, monkeypatch):
    monkeypatch.setattr(live, 'clinic_twilio_reminder_content_sid', 'HX-test')
    patient = patient_with_whatsapp(client, db_session)
    age_patient_messages(db_session, patient)
    appointment(db_session, patient, hours=25)
    send(db_session, NOW + timedelta(hours=1, minutes=1))
    message = reminder_messages(db_session, patient)[-1]
    assert message.metadata_json['delivery'] == 'queued'
    assert message.metadata_json['form'] == 'template'


def test_no_template_falls_back_to_sms_without_flooding_doctor(client, db_session, live, monkeypatch):
    sent = []
    monkeypatch.setattr(cr, 'get_sms_provider', lambda: _Sms(sent))
    patient = patient_with_whatsapp(client, db_session)
    age_patient_messages(db_session, patient)
    appt = appointment(db_session, patient, hours=25)
    send(db_session, NOW + timedelta(hours=1, minutes=1))
    assert reminder_messages(db_session, patient)[-1].metadata_json['delivery'] == 'blocked_no_template'
    assert sent and sent[0][0] == PHONE and 'kliniğimizi arayın' in sent[0][1]
    reminder = reminders(db_session, appt)[0]
    assert reminder.status == ReminderStatus.SENT
    conversation = db_session.scalar(select(ClinicConversation).where(ClinicConversation.patient_id == patient.id))
    assert conversation.status != ClinicConversationStatus.WAITING_HUMAN


def test_patient_without_whatsapp_gets_sms(db_session, monkeypatch):
    sent = []
    monkeypatch.setattr(cr, 'get_sms_provider', lambda: _Sms(sent))
    clinic = ensure_default_clinic(db_session)
    patient = ClinicPatient(clinic_id=clinic.id, phone='+905551119999', full_name='Telefon Hasta')
    db_session.add(patient)
    db_session.commit()
    appointment(db_session, patient, hours=25)
    assert send(db_session, NOW + timedelta(hours=1, minutes=1)) == 1
    assert sent[0][0] == '+905551119999'


def test_disabled_by_default_does_nothing(client, db_session):
    appt = appointment(db_session, patient_with_whatsapp(client, db_session), hours=25)
    assert cr.run(db_session, now=NOW) == {'planned': 0, 'sent': 0}
    assert reminders(db_session, appt) == []


def test_run_when_enabled(client, db_session, enabled):
    appointment(db_session, patient_with_whatsapp(client, db_session), hours=25)
    assert cr.run(db_session, now=NOW)['planned'] == 2


# ─── Hasta yanıtı ────────────────────────────────────────────────────────────


def reminded(client, db, *, slot=False, phone=PHONE):
    patient = patient_with_whatsapp(client, db, phone=phone)
    appt = appointment(db, patient, hours=25, slot=slot)
    send(db, NOW + timedelta(hours=1, minutes=1))
    # Yanıt penceresi "şimdi"ye göre ölçülür: gönderilen hatırlatmayı şimdiye çek.
    for r in reminders(db, appt):
        r.scheduled_for = datetime.now(timezone.utc) - timedelta(minutes=5)
    appt.starts_at = datetime.now(timezone.utc) + timedelta(hours=23)
    db.commit()
    return patient, appt


def ai_replies(db, patient):
    return sum(1 for m in db.scalars(select(ClinicMessage).where(
        ClinicMessage.sender == ClinicMessageSender.ASSISTANT)).all() if m.conversation.patient_id == patient.id)


def test_cancel_button_cancels_and_frees_slot_without_ai(client, db_session):
    patient, appt = reminded(client, db_session, slot=True)
    before = ai_replies(db_session, patient)
    data = whatsapp(client, 'İptal', extra={'ButtonPayload': 'r:cancel', 'ButtonText': 'İptal'})
    assert data['action'] == 'reminder_cancel'
    db_session.refresh(appt)
    assert appt.status == ClinicalAppointmentStatus.CANCELLED
    assert db_session.get(ClinicDoctorSlot, appt.slot_id).is_booked is False
    assert ai_replies(db_session, patient) == before  # yapay zekâ ikinci cevap üretmedi
    assert 'iptal edildi' in data['reply']


def test_confirm_records_attendance_without_bypassing_clinic_approval(client, db_session):
    """Hekimi atanmamış PENDING randevu hastanın düğmesiyle "onaylı" olmaz."""
    patient, appt = reminded(client, db_session)
    data = whatsapp(client, 'Geleceğim', extra={'ButtonPayload': f'r:confirm:{appt.id}'})
    assert data['action'] == 'reminder_confirm'
    db_session.refresh(appt)
    assert appt.status == ClinicalAppointmentStatus.PENDING
    assert appt.metadata_json['patient_attendance'] == 'confirmed'
    assert 'sizi bekliyoruz' in data['reply']


def test_reschedule_keeps_appointment_and_hands_to_human(client, db_session):
    patient, appt = reminded(client, db_session)
    data = whatsapp(client, 'Ertele', extra={'ButtonPayload': 'r:reschedule'})
    db_session.refresh(appt)
    assert appt.status == ClinicalAppointmentStatus.PENDING  # korunuyor
    conversation = db_session.get(ClinicConversation, data['conversation_id'])
    assert conversation.status == ClinicConversationStatus.WAITING_HUMAN
    assert conversation.metadata_json['reschedule_requested'] == appt.id
    assert 'korunuyor' in data['reply']


def test_short_typed_reply_is_understood(client, db_session):
    patient, appt = reminded(client, db_session)
    assert whatsapp(client, 'gelemeyeceğim')['action'] == 'reminder_cancel'


def test_long_question_goes_to_normal_flow(client, db_session):
    patient, appt = reminded(client, db_session)
    data = whatsapp(client, 'iptal edersem ücret alınır mı acaba?')
    assert not data['action'].startswith('reminder_')
    db_session.refresh(appt)
    assert appt.status == ClinicalAppointmentStatus.PENDING


def test_typed_cancel_without_recent_reminder_is_not_a_cancellation(client, db_session):
    patient = patient_with_whatsapp(client, db_session)
    appt = appointment(db_session, patient, hours=25)  # hatırlatma gönderilmedi
    data = whatsapp(client, 'iptal')
    assert not data['action'].startswith('reminder_')
    db_session.refresh(appt)
    assert appt.status == ClinicalAppointmentStatus.PENDING


def test_button_for_someone_elses_appointment_is_ignored(client, db_session):
    _, victim_appt = reminded(client, db_session, phone=OTHER)
    reminded(client, db_session, phone=PHONE)
    data = whatsapp(client, 'İptal', phone=PHONE, extra={'ButtonPayload': f'r:cancel:{victim_appt.id}'})
    assert data['action'] != 'reminder_cancel'
    db_session.refresh(victim_appt)
    assert victim_appt.status == ClinicalAppointmentStatus.PENDING


def test_duplicate_button_reply_processed_once(client, db_session):
    patient, appt = reminded(client, db_session)
    extra = {'ButtonPayload': 'r:confirm', 'MessageSid': 'SMDUPLICATE'}
    first = client.post('/api/webhooks/whatsapp', data={'From': f'whatsapp:{PHONE}', 'To': BUSINESS, 'Body': 'Geleceğim'} | extra,
                        headers={'Content-Type': 'application/x-www-form-urlencoded'}).json()
    second = client.post('/api/webhooks/whatsapp', data={'From': f'whatsapp:{PHONE}', 'To': BUSINESS, 'Body': 'Geleceğim'} | extra,
                         headers={'Content-Type': 'application/x-www-form-urlencoded'}).json()
    assert first['action'] == 'reminder_confirm' and second['action'] == 'duplicate_ignored'
    acks = [m for m in db_session.scalars(select(ClinicMessage)).all() if (m.metadata_json or {}).get('reminder_reply_ack')]
    assert len(acks) == 1


# ─── Yan etkiler ─────────────────────────────────────────────────────────────


def test_operator_cancel_also_frees_slot(client, db_session):
    patient = patient_with_whatsapp(client, db_session)
    appt = appointment(db_session, patient, hours=25, slot=True)
    set_clinical_appointment_status(db_session, ensure_default_clinic(db_session), appt.id, 'cancelled')
    assert db_session.get(ClinicDoctorSlot, appt.slot_id).is_booked is False


def test_meta_button_reply_is_no_longer_dropped():
    payload = {'entry': [{'changes': [{'value': {'metadata': {'phone_number_id': '1'}, 'contacts': [], 'messages': [
        {'from': '905551110001', 'id': 'wamid.B1', 'type': 'button', 'button': {'text': 'İptal', 'payload': 'r:cancel:7'}},
        {'from': '905551110001', 'id': 'wamid.B2', 'type': 'interactive',
         'interactive': {'type': 'button_reply', 'button_reply': {'id': 'r:confirm:7', 'title': 'Geleceğim'}}},
    ]}}]}]}
    parsed = parse_meta_payload(payload)
    assert [m.body for m in parsed] == ['İptal', 'Geleceğim']
    assert cr._button_action(parsed[0].raw_payload) == ('cancel', 7)
    assert cr._button_action(parsed[1].raw_payload) == ('confirm', 7)


class _Sms:
    def __init__(self, sent):
        self.sent = sent

    def send(self, *, to, body):
        from app.services.sms_service import SmsResult
        self.sent.append((to, body))
        return SmsResult(ok=True, provider='test')
