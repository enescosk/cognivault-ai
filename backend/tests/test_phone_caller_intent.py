"""Telefon hattında arayan niyeti (F1.6) — görüşmenin kendisi hakkındaki sorular.

Bu katmandan önce ölçülen davranış: "Robot musunuz?", "Hava durumu nasıl?",
"Yetkiliye bağlayın", "Bir daha aramayın" cümlelerinin **hepsi** aynı yanıtı
alıyordu — "Talebinizi doktor ekranına öncelikli olarak düşürdüm". Hem arayana
yanlış cevap, hem doktor ekranına gereksiz shadow review.

Korunan değişmezler (bu dosyanın asıl işi):
- ACİL turda bu katman ASLA devreye girmez.
- Belirti kelimesi geçen söz ("anlamadım, dişim ağrıyor") bu katmana düşmez;
  mevcut triyaj/eskalasyon yolu işler.
- Teklif aşamasında sözlü slot seçimi önceliklidir; niyet yanıtı verilse bile
  teklif durumu SİLİNMEZ — arayan bir sonraki turda hâlâ seçim yapabilir.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.ai.caller_intent import (
    PHONE_INTENTS,
    classify_caller_intent,
    conversational_only,
    stated_time,
)
from app.models import ClinicConversation, ClinicDoctor, ClinicDoctorSlot
from app.services.clinical_service import ensure_default_clinic


def _gather(client, speech: str, *, call_sid: str, from_phone: str = "%2B905329990001"):
    return client.post(
        "/api/webhooks/voice/gather",
        content=f"SpeechResult={speech}&From={from_phone}&To=%2B902120000000&CallSid={call_sid}",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )


def _conversation(db, call_sid: str) -> ClinicConversation:
    return db.scalars(
        select(ClinicConversation).where(ClinicConversation.external_thread_id == call_sid)
    ).first()


def _add_dental_slot(db, *, hours_ahead: float) -> ClinicDoctorSlot:
    clinic = ensure_default_clinic(db)
    doctor = db.scalars(
        select(ClinicDoctor).where(
            ClinicDoctor.clinic_id == clinic.id, ClinicDoctor.email == "intent@clinic.test"
        )
    ).first()
    if doctor is None:
        doctor = ClinicDoctor(
            clinic_id=clinic.id, full_name="Niyet Test", email="intent@clinic.test",
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


# ─── Sınıflandırıcı (saf birim) ──────────────────────────────────────────────


def test_allowed_filter_excludes_channel_intents():
    """`pricing` klinik hattında ingest'e ait — telefon alt kümesine girmez."""
    assert classify_caller_intent("Fiyat ne kadar?") == "pricing"
    assert classify_caller_intent("Fiyat ne kadar?", allowed=PHONE_INTENTS) is None


def test_allowed_filter_does_not_shadow_later_match():
    """Filtre eşleşmeden ÖNCE uygulanır: elenen kural gerçek eşleşmeyi gölgelemez."""
    # 'mesgulum' (busy, tabloda 6.) telefon alt kümesinde yok; elendiğinde
    # 'yetkiliye baglayin' (human, 7.) yine bulunmalı.
    text = "Mesgulum ama yetkiliye baglayin"
    assert classify_caller_intent(text) == "busy"
    assert classify_caller_intent(text, allowed=PHONE_INTENTS) == "human"


def test_conversational_gate_rejects_medical_signal():
    assert conversational_only("Anlamadım, tekrar eder misiniz?") is True
    assert conversational_only("Anlamadım, dişim çok ağrıyor") is False
    assert conversational_only("Robot musunuz? Yüzüm şişti") is False


def test_conversational_gate_rejects_long_utterance():
    """Uzun söylem neredeyse her zaman gerçek bir talep taşır."""
    long_text = "anlamadım " + " ".join(f"kelime{i}" for i in range(12))
    assert conversational_only(long_text) is False


def test_stated_time_reads_clock_from_raw_text():
    """Regresyon: normalize ':' siler, kalıp ham metinde aranmalı."""
    assert stated_time("15:30 uygun") is True
    assert stated_time("saat 15 uygundur") is True
    assert stated_time("önümüzdeki cuma") is True
    assert stated_time("bilemedim ki") is False


# ─── Telefon akışı (uçtan uca webhook) ───────────────────────────────────────


def test_identity_question_gets_honest_answer(client):
    response = _gather(client, "Kimsiniz+robot+musunuz", call_sid="CAintent1")
    assert response.status_code == 200
    assert "insan değilim" in response.text
    assert "doktor ekranına" not in response.text
    assert "<Gather" in response.text  # arama devam eder


def test_out_of_scope_is_redirected_not_escalated(client):
    response = _gather(client, "Hava+durumu+nasil", call_sid="CAintent2")
    assert response.status_code == 200
    assert "yardımcı olamıyorum" in response.text
    assert "doktor ekranına" not in response.text


def test_human_request_is_acknowledged(client):
    response = _gather(client, "Yetkiliye+baglayin+lutfen", call_sid="CAintent3")
    assert response.status_code == 200
    assert "klinik ekibimizden" in response.text


def test_stop_ends_the_call(client):
    response = _gather(client, "Bir+daha+aramayin", call_sid="CAintent4")
    assert response.status_code == 200
    assert "görüşmeyi burada bitiriyorum" in response.text
    assert "<Gather" not in response.text  # arama kapanır


def test_wrong_number_ends_the_call(client):
    response = _gather(client, "Yanlis+numara", call_sid="CAintent5")
    assert response.status_code == 200
    assert "yanlış numaraya" in response.text
    assert "<Gather" not in response.text


# ─── Güvenlik değişmezleri ───────────────────────────────────────────────────


def test_medical_content_never_reaches_conversational_layer(client):
    """"Anlamadım" kuralına takılan bir söz tıbbi içerik taşıyorsa yutulmaz."""
    response = _gather(client, "Anlamadim+disim+cok+agriyor", call_sid="CAintent6")
    assert response.status_code == 200
    assert "Elbette" not in response.text
    assert "doktor ekranına" in response.text


def test_emergency_turn_is_untouched(client):
    """Acil yol dokunulmaz: niyet kelimesi içerse bile eskalasyon konuşur."""
    response = _gather(
        client, "Kanama+durmuyor+nefes+alamiyorum+kimsiniz", call_sid="CAintent7"
    )
    assert response.status_code == 200
    assert "insan değilim" not in response.text


def test_offering_stage_survives_a_conversational_turn(client, db_session):
    """Teklif okunduktan sonra "tekrar eder misiniz" teklifleri yineler ve
    durumu korur — arayan bir sonraki turda hâlâ seçim yapabilir."""
    _add_dental_slot(db_session, hours_ahead=26)
    first = _gather(client, "Randevu+almak+istiyorum", call_sid="CAintent8")
    assert "müsait randevu saatleri" in first.text

    repeated = _gather(client, "Tekrar+eder+misiniz", call_sid="CAintent8")
    assert repeated.status_code == 200
    assert "tekrar ediyorum" in repeated.text.lower()
    assert "müsait randevu saatleri" in repeated.text

    db_session.expire_all()
    conversation = _conversation(db_session, "CAintent8")
    stage = ((conversation.metadata_json or {}).get("phone_flow") or {}).get("stage")
    assert stage == "offering"


def test_slot_selection_still_wins_in_offering_stage(client, db_session):
    """Sözlü seçim önceliklidir; niyet katmanı araya girmez."""
    _add_dental_slot(db_session, hours_ahead=26)
    _gather(client, "Randevu+almak+istiyorum", call_sid="CAintent9")
    selection = _gather(client, "birincisi", call_sid="CAintent9")
    assert selection.status_code == 200
    assert "randevunuzu oluşturdum" in selection.text.lower()
