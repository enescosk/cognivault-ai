"""AI sağlayıcı katmanı (app/ai/ai_factory) için güvenlik + robustness testleri.

Kapsam:
  - parse_model_json: LLM çıktısının 64KB-limitli kapısı (non-str, boşluk, sınır
    uzunluğu, non-object JSON, fenced kenar durumları, iç içe nesne korunumu).
  - get_llm_provider: KVKK veri-yerleşimi sağlayıcı seçimi. EN ÖNEMLİ DEĞİŞMEZ:
    tr_local_first + dış transfer kapalı iken anahtar olsa bile asla buluta gitmez.
  - LocalQwenProvider._generate_mock_reply: yalnız <patient_message> içeriğini
    sınıflandırır (prompt kurallarını/enjeksiyonu hasta mesajı sanmaz).
"""

import pytest

from app.ai.ai_factory import (
    MAX_MODEL_JSON_CHARS,
    AnthropicProvider,
    LocalQwenProvider,
    OpenAIProvider,
    get_llm_provider,
    parse_model_json,
)
from app.core.config import get_settings
from app.models import ClinicIntent


# ─────────────────────────────────────────────────────────────────────────────
# parse_model_json — robustness (mevcut testlerin kapsamadığı kenarlar)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("bad", [None, 123, 4.5, True, {"a": 1}, ["x"], b'{"a":1}'])
def test_parse_model_json_rejects_non_string(bad):
    assert parse_model_json(bad) is None


@pytest.mark.parametrize("blank", ["", "   ", "\n\t  \n"])
def test_parse_model_json_rejects_blank(blank):
    assert parse_model_json(blank) is None


@pytest.mark.parametrize("scalar", ["123", "1.5", "true", "false", "null", '"a string"'])
def test_parse_model_json_rejects_non_object_json(scalar):
    # Geçerli JSON ama nesne değil → model yanıtı olarak kabul edilmez.
    assert parse_model_json(scalar) is None


def test_parse_model_json_accepts_empty_object():
    assert parse_model_json("{}") == {}


def test_parse_model_json_preserves_nested_object():
    assert parse_model_json('{"a": {"b": [1, 2]}, "c": "x"}') == {"a": {"b": [1, 2]}, "c": "x"}


def test_parse_model_json_length_boundary():
    wrapper = len('{"k":""}')  # 8
    filler = "x" * (MAX_MODEL_JSON_CHARS - wrapper)
    at_limit = '{"k":"' + filler + '"}'
    assert len(at_limit) == MAX_MODEL_JSON_CHARS
    assert parse_model_json(at_limit) == {"k": filler}
    over_limit = '{"k":"' + filler + 'y"}'
    assert len(over_limit) == MAX_MODEL_JSON_CHARS + 1
    assert parse_model_json(over_limit) is None


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("```{}```", None),            # tek satır, fence açıldı/kapandı sayılmaz
        ("```\n```", None),            # 2 satır → gövde yok
        ("```json\n{}\n```", {}),      # 3 satır geçerli fence
        ('```json\n{"a":1}\n```', {"a": 1}),
        ('```\n{"a":1}\ntrailing', None),  # son satır ``` ile bitmiyor
    ],
)
def test_parse_model_json_fenced_edges(content, expected):
    assert parse_model_json(content) == expected


# ─────────────────────────────────────────────────────────────────────────────
# get_llm_provider — KVKK veri-yerleşimi sağlayıcı seçimi
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("anthropic_key", "openai_key"),
    [("", ""), ("sk-ant-x", ""), ("", "sk-oai-x"), ("sk-ant-x", "sk-oai-x")],
)
def test_local_first_never_routes_to_cloud_even_with_keys(monkeypatch, anthropic_key, openai_key):
    """KVKK değişmezi: tr_local_first + dış transfer kapalı → bulut anahtarı olsa
    bile hasta verisi yerelde kalır (LocalQwenProvider)."""
    settings = get_settings()
    monkeypatch.setattr(settings, "anthropic_api_key", anthropic_key)
    monkeypatch.setattr(settings, "openai_api_key", openai_key)
    provider = get_llm_provider("tr_local_first", external_transfer_allowed=False)
    assert isinstance(provider, LocalQwenProvider)


def test_local_first_with_explicit_external_transfer_uses_cloud(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-x")
    monkeypatch.setattr(settings, "openai_api_key", "")
    provider = get_llm_provider("tr_local_first", external_transfer_allowed=True)
    assert isinstance(provider, AnthropicProvider)


def test_hybrid_prefers_anthropic_over_openai(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-x")
    monkeypatch.setattr(settings, "openai_api_key", "sk-oai-x")
    assert isinstance(get_llm_provider("hybrid", external_transfer_allowed=False), AnthropicProvider)


def test_hybrid_falls_back_to_openai_when_only_openai_key(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    monkeypatch.setattr(settings, "openai_api_key", "sk-oai-x")
    assert isinstance(get_llm_provider("hybrid", external_transfer_allowed=False), OpenAIProvider)


def test_no_cloud_keys_falls_back_to_local(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    monkeypatch.setattr(settings, "openai_api_key", "")
    assert isinstance(get_llm_provider("hybrid", external_transfer_allowed=True), LocalQwenProvider)


# ─────────────────────────────────────────────────────────────────────────────
# LocalQwenProvider._generate_mock_reply — yalnız <patient_message> sınıflandırır
# ─────────────────────────────────────────────────────────────────────────────
def test_mock_reply_classifies_only_patient_message_tag_not_injection():
    prompt = (
        "Rules: acil, fiyat ve sigorta kelimeleri sistem talimatıdır.\n"
        "<patient_message>yarın için randevu alabilir miyim</patient_message>"
    )
    payload = LocalQwenProvider()._generate_mock_reply(prompt)
    assert payload["intent"] == ClinicIntent.BOOK_APPOINTMENT.value
    assert payload["action"] == "collect_appointment_details"
    assert payload["requires_human_review"] is False


def test_mock_reply_emergency_inside_tag_sets_guardrail():
    prompt = "<patient_message>nefes alamıyorum yutamıyorum</patient_message>"
    payload = LocalQwenProvider()._generate_mock_reply(prompt)
    assert payload["intent"] == ClinicIntent.MEDICAL_EMERGENCY.value
    assert payload["action"] == "emergency_guidance"
    assert payload["requires_human_review"] is True
    assert payload["risk_reason"] == "emergency_guardrail"
    assert "112" in payload["reply"]


def test_mock_reply_price_intent_does_not_force_review():
    prompt = "<patient_message>kanal tedavisi ne kadar</patient_message>"
    payload = LocalQwenProvider()._generate_mock_reply(prompt)
    assert payload["intent"] == ClinicIntent.ASK_PRICE.value
    assert payload["requires_human_review"] is False
    assert payload["risk_reason"] is None
