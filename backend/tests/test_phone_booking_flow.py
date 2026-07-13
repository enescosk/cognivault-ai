"""Telefonda randevu kapanışı (Yol A) — çok-turlu slot akışı + native TTS TwiML.

Değişmezler:
- Randevu niyeti → teklifler sesli okunur, durum conversation metadata'sında.
- Sözlü seçim ("birincisi", "yarın 9", gün adı) doğru teklife bağlanır;
  eşleşmeyen seçimde YANLIŞ slota bağlanmak yerine teklifler tekrar okunur.
- Onay: gerçek takvim slotu kilitlenir, randevu PENDING yaratılır, SMS gider,
  arama Gather'sız kibar kapanışla biter.
- Acil turda randevu akışı ASLA araya girmez; bekleyen seçim durumu temizlenir.
- Native TTS açıkken TwiML <Play>/tts/{sha}.wav üretir; sentez yoksa <Say>.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.models import (
    ClinicConversation,
    ClinicDoctor,
    ClinicDoctorSlot,
    ClinicalAppointment,
    ClinicalSlotOffer,
    ClinicalSlotOfferStatus,
)
from app.services import voice_prompt_cache
from app.services.clinical_service import ensure_default_clinic
from app.services.phone_flow_service import match_spoken_slot


def _gather(client, speech: str, *, call_sid: str = "CAbook1", from_phone: str = "%2B905321234567"):
    return client.post(
        "/api/webhooks/voice/gather",
        content=f"SpeechResult={speech}&From={from_phone}&To=%2B902120000000&CallSid={call_sid}",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )


def _add_dental_slot(db, *, hours_ahead: float) -> ClinicDoctorSlot:
    clinic = ensure_default_clinic(db)
    doctor = db.scalars(
        select(ClinicDoctor).where(ClinicDoctor.clinic_id == clinic.id, ClinicDoctor.email == "tel@clinic.test")
    ).first()
    if doctor is None:
        doctor = ClinicDoctor(
            clinic_id=clinic.id, full_name="Telefon Test", email="tel@clinic.test",
            specialty="Diş Hekimliği", title="Dr.", is_active=True,
        )
        db.add(doctor)
        db.flush()
    start = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=hours_ahead)
    slot = ClinicDoctorSlot(
        clinic_id=clinic.id, doctor_id=doctor.id,
        start_time=start, end_time=start + timedelta(minutes=30),
    )
    db.add(slot)
    db.commit()
    db.refresh(slot)
    return slot


def _conversation(db, call_sid: str) -> ClinicConversation:
    return db.scalars(
        select(ClinicConversation).where(ClinicConversation.external_thread_id == call_sid)
    ).first()


# ─── Uçtan uca akış ──────────────────────────────────────────────────────────

def test_phone_booking_two_turns_creates_appointment(client, db_session):
    slot = _add_dental_slot(db_session, hours_ahead=26)

    first = _gather(client, "Randevu+almak+istiyorum+dis+temizligi+icin", call_sid="CAbook1")
    assert first.status_code == 200
    assert "müsait randevu saatleri" in first.text
    assert "birinci" in first.text
    assert "<Gather" in first.text

    conversation = _conversation(db_session, "CAbook1")
    flow = (conversation.metadata_json or {}).get("phone_flow") or {}
    assert flow.get("stage") == "offering"
    assert flow.get("offer_ids")

    second = _gather(client, "birincisi+olsun", call_sid="CAbook1")
    assert second.status_code == 200
    assert "randevunuzu oluşturdum" in second.text
    assert "<Gather" not in second.text  # kapanış — arama biter

    db_session.expire_all()
    appointment = db_session.scalars(
        select(ClinicalAppointment).order_by(ClinicalAppointment.id.desc())
    ).first()
    assert appointment is not None
    assert appointment.metadata_json.get("source") == "phone_call"
    assert appointment.slot_id == slot.id
    booked = db_session.get(ClinicDoctorSlot, slot.id)
    assert booked.is_booked is True
    offer = db_session.get(ClinicalSlotOffer, appointment.metadata_json["slot_offer_id"])
    assert offer.status == ClinicalSlotOfferStatus.CONSUMED

    flow = (_conversation(db_session, "CAbook1").metadata_json or {}).get("phone_flow") or {}
    assert flow.get("stage") == "booked"


def _confirmed_bookings(db):
    """Slot'a bağlanmış (telefonda ONAYLANMIŞ) randevular — pipeline'ın doktor
    ekranı taslağı (slot_id=None) sayılmaz."""
    return [
        a for a in db.scalars(select(ClinicalAppointment)).all()
        if a.slot_id is not None or (a.metadata_json or {}).get("confirmed_via") == "voice_webhook"
    ]


def test_unmatched_low_confidence_turn_escalates_not_reprompts(client, db_session):
    """Güvenlik-öncelikli kural: eşleşmeyen VE shadow-review üreten söylem
    ("hmm bilemedim" dahil) eskalasyon yanıtına düşer — riskli bir ifadeye
    ("nefes almakta zorlanıyorum") slot listesi okunması yapısal olarak imkânsız."""
    _add_dental_slot(db_session, hours_ahead=26)
    _gather(client, "Randevu+almak+istiyorum", call_sid="CAbook2")

    second = _gather(client, "hmm+bilemedim+ki", call_sid="CAbook2")
    assert second.status_code == 200
    assert "doktor ekranına" in second.text  # eskalasyon konuşuldu
    assert "müsait randevu saatleri" not in second.text
    db_session.expire_all()
    # Stage silinmedi — arayan bir sonraki turda yine seçim yapabilir.
    conversation = _conversation(db_session, "CAbook2")
    assert ((conversation.metadata_json or {}).get("phone_flow") or {}).get("stage") == "offering"
    assert _confirmed_bookings(db_session) == []


def test_unmatched_without_shadow_reprompts_offers(client, db_session):
    """Shadow üretmeyen eşleşmesiz söylemde teklifler tekrar okunur (birim)."""
    from app.services.clinical_service import IngestionResult
    from app.services.phone_flow_service import handle_phone_turn

    _add_dental_slot(db_session, hours_ahead=26)
    _gather(client, "Randevu+almak+istiyorum", call_sid="CAbook2b")
    db_session.expire_all()
    conversation = _conversation(db_session, "CAbook2b")
    clinic = ensure_default_clinic(db_session)
    patient = conversation.patient

    result = IngestionResult(
        clinic=clinic, patient=patient, conversation=conversation,
        message=None, action="auto_reply", reply="...", shadow_review=None,
    )
    outcome = handle_phone_turn(db_session, result, "şey acaba hangisi iyi olur")
    assert outcome is not None
    assert outcome.stage == "offering"
    assert "Tam anlayamadım" in outcome.reply
    assert "müsait randevu saatleri" in outcome.reply


def test_emergency_turn_never_enters_booking_and_clears_stage(client, db_session):
    _add_dental_slot(db_session, hours_ahead=26)
    _gather(client, "Randevu+almak+istiyorum", call_sid="CAbook3")
    conversation = _conversation(db_session, "CAbook3")
    assert (conversation.metadata_json or {}).get("phone_flow")

    emergency = _gather(client, "kanama+bir+türlü+durmuyor+nefes+alamıyorum", call_sid="CAbook3")
    assert emergency.status_code == 200
    assert "randevunuzu oluşturdum" not in emergency.text
    db_session.expire_all()
    conversation = _conversation(db_session, "CAbook3")
    # Acil eskalasyonda bekleyen seçim durumu temizlenir — sonraki "birincisi"
    # bayat tekliflere bağlanamaz.
    assert not ((conversation.metadata_json or {}).get("phone_flow") or {}).get("stage") == "offering"
    assert _confirmed_bookings(db_session) == []


def test_slot_taken_between_turns_apologizes_and_reoffers(client, db_session):
    slot = _add_dental_slot(db_session, hours_ahead=26)
    _add_dental_slot(db_session, hours_ahead=27)
    _gather(client, "Randevu+almak+istiyorum", call_sid="CAbook4")

    row = db_session.get(ClinicDoctorSlot, slot.id)
    row.is_booked = True  # başka kanal doldurdu
    db_session.add(row)
    db_session.commit()

    second = _gather(client, "birincisi", call_sid="CAbook4")
    assert second.status_code == 200
    assert "az önce doldu" in second.text
    assert "müsait randevu saatleri" in second.text  # taze teklifler okunur
    db_session.expire_all()
    assert _confirmed_bookings(db_session) == []


# ─── Sözlü eşleme birimi ─────────────────────────────────────────────────────

def _offer(db, starts_at_utc_naive: datetime) -> ClinicalSlotOffer:
    clinic = ensure_default_clinic(db)
    offer = ClinicalSlotOffer(
        clinic_id=clinic.id, department="Genel Diş Hekimliği",
        physician_name="Dr. Test",
        starts_at=starts_at_utc_naive,
        ends_at=starts_at_utc_naive + timedelta(minutes=30),
        status=ClinicalSlotOfferStatus.OFFERED,
        expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=15),
        metadata_json={},
    )
    db.add(offer)
    db.commit()
    db.refresh(offer)
    return offer


def test_match_ordinal_and_any(db_session):
    base = datetime(2026, 7, 21, 6, 0)  # 09:00 İstanbul (Salı)
    offers = [_offer(db_session, base), _offer(db_session, base + timedelta(hours=1))]
    assert match_spoken_slot("ikincisi lütfen", offers) is offers[1]
    assert match_spoken_slot("fark etmez siz seçin", offers) is offers[0]
    assert match_spoken_slot("ilk uygun olan", offers) is offers[0]


def test_match_spoken_hour_variants(db_session):
    nine = _offer(db_session, datetime(2026, 7, 21, 6, 0))    # 09:00 TR
    nine30 = _offer(db_session, datetime(2026, 7, 21, 6, 30))  # 09:30 TR
    fourteen = _offer(db_session, datetime(2026, 7, 21, 11, 0))  # 14:00 TR
    offers = [nine, nine30, fourteen]
    assert match_spoken_slot("dokuz buçuk olsun", offers) is nine30
    assert match_spoken_slot("saat 14 olur", offers) is fourteen
    assert match_spoken_slot("9.30 uygun", offers) is nine30
    # Var olmayan saat: yanlış slota bağlanmak yerine None
    assert match_spoken_slot("saat 18", offers) is None


def test_match_weekday(db_session):
    tuesday = _offer(db_session, datetime(2026, 7, 21, 6, 0))   # Salı
    wednesday = _offer(db_session, datetime(2026, 7, 22, 6, 0))  # Çarşamba
    assert match_spoken_slot("çarşamba günü olsun", [tuesday, wednesday]) is wednesday


# ─── Native TTS TwiML ────────────────────────────────────────────────────────

@pytest.fixture()
def native_tts(monkeypatch):
    s = get_settings()
    original = s.voice_phone_native_tts_enabled
    s.voice_phone_native_tts_enabled = True
    voice_prompt_cache.clear_cache()

    class _FakeTTS:
        def synthesize(self, text, voice=None):
            return b"RIFFfakewav", "audio/wav"

    import app.ai.voice_factory as vf

    monkeypatch.setattr(vf, "get_tts_provider", lambda *a, **k: _FakeTTS())
    yield s
    s.voice_phone_native_tts_enabled = original
    voice_prompt_cache.clear_cache()


def test_twiml_uses_play_with_cached_audio(client, db_session, native_tts):
    res = client.post(
        "/api/webhooks/voice/incoming",
        content="From=%2B905321234567&To=%2B902120000000&CallSid=CAtts1",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert res.status_code == 200
    assert "<Play>/api/webhooks/voice/tts/" in res.text
    # KVKK anonsu native seste de mevcut (metin sentezlenen içerikte)
    key = res.text.split("/api/webhooks/voice/tts/")[1].split(".wav")[0]

    audio = client.get(f"/api/webhooks/voice/tts/{key}.wav")
    assert audio.status_code == 200
    assert audio.headers["content-type"].startswith("audio/wav")
    assert audio.content == b"RIFFfakewav"


def test_tts_endpoint_404_for_unknown_key(client):
    res = client.get(f"/api/webhooks/voice/tts/{'0' * 64}.wav")
    assert res.status_code == 404


def test_twiml_falls_back_to_say_when_synthesis_fails(client, db_session, native_tts, monkeypatch):
    import app.ai.voice_factory as vf

    class _BrokenTTS:
        def synthesize(self, text, voice=None):
            raise RuntimeError("model yok")

    monkeypatch.setattr(vf, "get_tts_provider", lambda *a, **k: _BrokenTTS())
    voice_prompt_cache.clear_cache()
    res = client.post(
        "/api/webhooks/voice/incoming",
        content="From=%2B905321234567&To=%2B902120000000&CallSid=CAtts2",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert res.status_code == 200
    assert "<Play>" not in res.text
    assert '<Say language="tr-TR"' in res.text  # arama sessiz kalmaz