"""Klinik AI güvenlik katmanı (app/services/clinical_ai_service) değişmez testleri.

Bunlar "AI çıktısına güvenme" sözleşmesini doğrular:
  - _validated_provider_result: model JSON'ı güvenli karara dönüştüren kapı.
      * Deterministik ACİL kararı modelce DÜŞÜRÜLEMEZ.
      * Yüksek güvenli deterministik intent çelişkide kazanır; düşük güvende model
        benimsenir ama insan incelemesi bayraklanır.
      * action HER ZAMAN güvenli allowlist'ten gelir (model rastgele action enjekte edemez).
      * confidence clamp + NaN/inf güvenli; eşik altı insan incelemesine gider.
      * Güvensiz tıbbi tavsiye / prompt-leak / aşırı uzun yanıt güvenli şablonla değişir.
  - _contains_unsafe_medical_advice: ilaç/doz/teşhis kalıpları + yanlış-pozitif sınırları.
  - _safe_reply, _looks_like_planning_reply, detect_frustration yardımcıları.
"""

import pytest
from types import SimpleNamespace

from app.models import ClinicIntent
from app.services.clinical_persona_service import choose_persona
from app.services.clinical_ai_service import (
    _contains_unsafe_medical_advice,
    _looks_like_planning_reply,
    _safe_reply,
    _validated_provider_result,
    detect_frustration,
)


def _clinic(threshold: float = 0.9) -> SimpleNamespace:
    return SimpleNamespace(
        ai_auto_reply_threshold=threshold,
        name="Test Klinik",
        emergency_disclaimer="Please call emergency services.",
    )


def _validate(payload, intent, confidence, *, threshold=0.9, language="tr"):
    return _validated_provider_result(
        payload,
        deterministic_intent=intent,
        deterministic_confidence=confidence,
        language=language,
        clinic=_clinic(threshold),
        persona=choose_persona(intent),
    )


# ─────────────────────────────────────────────────────────────────────────────
# _validated_provider_result — güvenlik değişmezleri
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("payload", [None, [], "string", 123, ("a", "b")])
def test_non_dict_payload_returns_none(payload):
    assert _validate(payload, ClinicIntent.GENERAL_QUESTION, 0.5) is None


def test_high_confidence_deterministic_wins_on_conflict():
    result = _validate(
        {"reply": "Fiyat bilgisi vereyim.", "confidence": 0.7, "intent": "ask_price"},
        ClinicIntent.BOOK_APPOINTMENT,
        0.90,  # >= 0.85 → deterministik kazanır
    )
    assert result.intent == ClinicIntent.BOOK_APPOINTMENT
    assert result.action == "collect_appointment_details"
    assert result.requires_human_review is True
    assert result.risk_reason == "model_rule_intent_conflict"


def test_low_confidence_deterministic_adopts_model_intent_but_flags_review():
    result = _validate(
        {"reply": "Tedavi fiyatı işleme göre değişir.", "confidence": 0.9, "intent": "ask_price"},
        ClinicIntent.GENERAL_QUESTION,
        0.50,  # < 0.85 → model intent benimsenir
    )
    assert result.intent == ClinicIntent.ASK_PRICE
    assert result.action == "collect_service_for_price"
    assert result.requires_human_review is True
    assert result.risk_reason == "model_rule_intent_conflict"


def test_invalid_model_intent_falls_back_and_flags():
    result = _validate(
        {"reply": "Size yardımcı olayım.", "confidence": 0.95, "intent": "totally_made_up"},
        ClinicIntent.GENERAL_QUESTION,
        0.95,
    )
    assert result.intent == ClinicIntent.GENERAL_QUESTION
    assert result.requires_human_review is True
    assert result.risk_reason == "invalid_model_intent"


def test_confidence_below_threshold_requires_review():
    result = _validate(
        {"reply": "Hangi şube için adres istiyorsunuz?", "confidence": 0.4, "intent": "ask_location"},
        ClinicIntent.ASK_LOCATION,
        0.6,
        threshold=0.9,
    )
    assert result.requires_human_review is True
    assert result.risk_reason == "confidence_below_auto_reply_threshold"


def test_confident_consistent_reply_is_auto_send_eligible():
    result = _validate(
        {"reply": "Hangi şube için adres istiyorsunuz?", "confidence": 0.95, "intent": "ask_location"},
        ClinicIntent.ASK_LOCATION,
        0.95,
        threshold=0.9,
    )
    assert result.requires_human_review is False
    assert result.risk_reason is None


def test_confidence_is_max_of_model_and_deterministic_without_conflict():
    result = _validate(
        {"reply": "Hangi şube?", "confidence": 0.30, "intent": "ask_location"},
        ClinicIntent.ASK_LOCATION,
        0.80,
        threshold=0.5,
    )
    assert result.confidence == 0.80
    assert result.requires_human_review is False


def test_planning_reply_leak_is_replaced_with_safe_template():
    leaked = "Şu anki plan görüntüleniyor, neleri değiştirmek istersiniz?"
    result = _validate(
        {"reply": leaked, "confidence": 0.95, "intent": "general_question"},
        ClinicIntent.GENERAL_QUESTION,
        0.66,
        threshold=0.5,
    )
    assert "neleri değiştirmek" not in result.reply
    assert result.reply.strip()


def test_overlong_reply_is_replaced():
    result = _validate(
        {"reply": "A" * 1300, "confidence": 0.95, "intent": "general_question"},
        ClinicIntent.GENERAL_QUESTION,
        0.9,
        threshold=0.5,
    )
    assert len(result.reply) <= 1200
    assert "AAAA" not in result.reply


@pytest.mark.parametrize(
    ("intent", "action"),
    [
        (ClinicIntent.MEDICAL_EMERGENCY, "emergency_guidance"),
        (ClinicIntent.BOOK_APPOINTMENT, "collect_appointment_details"),
        (ClinicIntent.RESCHEDULE_APPOINTMENT, "collect_reschedule_details"),
        (ClinicIntent.CANCEL_APPOINTMENT, "collect_cancellation_details"),
        (ClinicIntent.ASK_PRICE, "collect_service_for_price"),
        (ClinicIntent.ASK_INSURANCE, "collect_insurance_type"),
        (ClinicIntent.ASK_LOCATION, "collect_branch"),
        (ClinicIntent.ASK_WORKING_HOURS, "collect_branch"),
        (ClinicIntent.GENERAL_QUESTION, "collect_info"),
        (ClinicIntent.UNKNOWN, "clarify_request"),
    ],
)
def test_action_always_from_allowlist_not_model(intent, action):
    # Model "rm -rf /" gibi rastgele action verse de güvenli haritadan gelir.
    result = _validate(
        {"reply": "Yanıt.", "confidence": 0.95, "intent": intent.value, "action": "rm -rf /"},
        intent,
        0.95,
        threshold=0.5,
    )
    assert result.action == action


def test_model_data_non_dict_becomes_empty():
    result = _validate(
        {"reply": "x", "confidence": 0.9, "intent": "general_question", "data": [1, 2]},
        ClinicIntent.GENERAL_QUESTION,
        0.9,
        threshold=0.5,
    )
    assert result.data == {}


def test_model_data_dict_is_preserved():
    result = _validate(
        {"reply": "x", "confidence": 0.9, "intent": "general_question", "data": {"missing_fields": ["phone"]}},
        ClinicIntent.GENERAL_QUESTION,
        0.9,
        threshold=0.5,
    )
    assert result.data == {"missing_fields": ["phone"]}


# ─────────────────────────────────────────────────────────────────────────────
# _contains_unsafe_medical_advice — ilaç / doz / teşhis kalıpları
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "unsafe",
    [
        "Antibiyotik kullanın lütfen.",
        "Ağrı kesici alın.",
        "Günde 500 mg alın.",
        "2 tablet yeterli olur.",
        "10 ml damla kullanın.",
        "Kesin enfeksiyon var.",
        "Teşhisiniz çürük.",
        "This is definitely diagnosis.",
    ],
)
def test_unsafe_medical_patterns_detected(unsafe):
    assert _contains_unsafe_medical_advice(unsafe) is True


@pytest.mark.parametrize(
    "safe",
    [
        "Randevu için hangi gün uygun olur?",
        "Fiyat bilgisi için işlem türünü paylaşır mısınız?",
        "Lütfen 112'yi arayın veya en yakın acil servise başvurun.",
        "Diş etinizdeki kanamayı hekime öncelikli not düşüyorum.",
        "Saat 14:30 randevunuz uygun mu?",
    ],
)
def test_safe_replies_not_flagged_as_unsafe(safe):
    assert _contains_unsafe_medical_advice(safe) is False


# ─────────────────────────────────────────────────────────────────────────────
# _safe_reply — deterministik güvenli şablonlar
# ─────────────────────────────────────────────────────────────────────────────
def test_safe_reply_emergency_tr_contains_112():
    reply = _safe_reply(ClinicIntent.MEDICAL_EMERGENCY, "tr", _clinic(), choose_persona(ClinicIntent.MEDICAL_EMERGENCY))
    assert "112" in reply


def test_safe_reply_en_emergency_uses_clinic_disclaimer():
    clinic = _clinic()
    reply = _safe_reply(ClinicIntent.MEDICAL_EMERGENCY, "en", clinic, choose_persona(ClinicIntent.MEDICAL_EMERGENCY))
    assert reply == clinic.emergency_disclaimer


@pytest.mark.parametrize("intent", list(ClinicIntent))
def test_safe_reply_is_nonempty_for_every_intent(intent):
    reply = _safe_reply(intent, "tr", _clinic(), choose_persona(intent))
    assert isinstance(reply, str) and reply.strip()


# ─────────────────────────────────────────────────────────────────────────────
# _looks_like_planning_reply — prompt/akıl yürütme sızıntısı tespiti
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "reply",
    [
        "Şu anki plan görüntüleniyor, neleri değiştirmek istersiniz?",
        "Brainstorming raporu hazır.",
        "Adımlar: (1) randevu (2) onay (3) sms",
    ],
)
def test_planning_reply_detected(reply):
    assert _looks_like_planning_reply(reply) is True


@pytest.mark.parametrize(
    "reply",
    [
        "Randevu için hangi gün uygun olur?",
        "Fiyat bilgisi için işlem türünü paylaşır mısınız?",
    ],
)
def test_normal_reply_not_flagged_as_planning(reply):
    assert _looks_like_planning_reply(reply) is False


# ─────────────────────────────────────────────────────────────────────────────
# detect_frustration — eskalasyon sinyali
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "text",
    [
        "Çok sinirliyim artık",
        "Bu ne rezalet bir hizmet",
        "Neden cevap vermiyorsunuz",
        "Saatlerdir bekliyorum",
        "Şikayet edeceğim sizi",
    ],
)
def test_frustration_detected(text):
    assert detect_frustration(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "Randevu almak istiyorum",
        "Teşekkür ederim çok iyisiniz",
        "Fiyat bilgisi alabilir miyim",
    ],
)
def test_calm_messages_not_flagged_as_frustration(text):
    assert detect_frustration(text) is False
