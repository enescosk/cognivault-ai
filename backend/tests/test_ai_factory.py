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
from types import SimpleNamespace

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
from app.services import clinical_ai_service


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
    monkeypatch.setattr(settings, "clinical_external_ai_allowed", True)
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-x")
    monkeypatch.setattr(settings, "openai_api_key", "")
    provider = get_llm_provider("tr_local_first", external_transfer_allowed=True)
    assert isinstance(provider, AnthropicProvider)


def test_hybrid_prefers_anthropic_over_openai(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "clinical_external_ai_allowed", True)
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-x")
    monkeypatch.setattr(settings, "openai_api_key", "sk-oai-x")
    assert isinstance(get_llm_provider("hybrid", external_transfer_allowed=True), AnthropicProvider)


def test_hybrid_falls_back_to_openai_when_only_openai_key(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "clinical_external_ai_allowed", True)
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    monkeypatch.setattr(settings, "openai_api_key", "sk-oai-x")
    assert isinstance(get_llm_provider("hybrid", external_transfer_allowed=True), OpenAIProvider)


def test_no_cloud_keys_falls_back_to_local(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "clinical_external_ai_allowed", True)
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    monkeypatch.setattr(settings, "openai_api_key", "")
    assert isinstance(get_llm_provider("hybrid", external_transfer_allowed=True), LocalQwenProvider)


def test_hybrid_without_app_level_switch_stays_local_even_with_clinic_consent(monkeypatch):
    """KVKK değişmezi: klinik `allow_cross_border_processors` rızası tek başına
    yetmez — platform-seviyesi `clinical_external_ai_allowed` kapalıysa (varsayılan),
    anahtarlar mevcut olsa bile bulut sağlayıcıya asla gidilmez."""
    settings = get_settings()
    monkeypatch.setattr(settings, "clinical_external_ai_allowed", False)
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-x")
    monkeypatch.setattr(settings, "openai_api_key", "sk-oai-x")
    assert isinstance(get_llm_provider("hybrid", external_transfer_allowed=True), LocalQwenProvider)
    assert isinstance(get_llm_provider("tr_local_first", external_transfer_allowed=True), LocalQwenProvider)


def test_hybrid_without_clinic_consent_stays_local_even_with_app_switch_on(monkeypatch):
    """Tersi yön: platform-seviyesi `clinical_external_ai_allowed` açık olsa bile
    klinik sınır-ötesi rızası (`external_transfer_allowed`) yoksa bulut sağlayıcıya
    gidilmez."""
    settings = get_settings()
    monkeypatch.setattr(settings, "clinical_external_ai_allowed", True)
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-x")
    monkeypatch.setattr(settings, "openai_api_key", "sk-oai-x")
    assert isinstance(get_llm_provider("hybrid", external_transfer_allowed=False), LocalQwenProvider)


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


def test_openai_is_used_only_as_policy_allowed_local_fallback(monkeypatch):
    class UnavailableLocal:
        def generate_chat_reply(self, *args, **kwargs):
            return {
                "_provider_source": "deterministic_local_fallback",
                "reply": "Yerel sabit cevap",
                "confidence": 0.7,
                "intent": "ask_location",
                "requires_human_review": False,
                "data": {},
            }

    class WorkingOpenAI:
        def generate_chat_reply(self, *args, **kwargs):
            return {
                "_provider_source": "openai",
                "reply": "Kliniğin hangi şubesinin konumunu istersiniz?",
                "confidence": 0.95,
                "intent": "ask_location",
                "requires_human_review": False,
                "data": {},
            }

    settings = get_settings()
    monkeypatch.setattr(settings, "clinical_ai_enabled", True)
    monkeypatch.setattr(settings, "clinical_external_ai_allowed", True)
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(clinical_ai_service, "get_llm_provider", lambda *_: UnavailableLocal())
    monkeypatch.setattr(clinical_ai_service, "OpenAIProvider", WorkingOpenAI)
    clinic = SimpleNamespace(
        name="Test Klinik",
        default_language="tr",
        ai_auto_reply_threshold=0.9,
        emergency_disclaimer="Call emergency services.",
        organization_id=None,
        settings_json={
            "data_residency_mode": "hybrid_explicit_consent",
            "allow_cross_border_processors": True,
        },
    )

    result = clinical_ai_service.generate_clinical_reply(
        clinic,
        "Konumunuz nerede?",
        external_ai_consent=True,
    )

    assert result.data["provider_source"] == "openai"
    assert [step["status"] for step in result.data["provider_trace"]] == [
        "held_as_safe_fallback",
        "selected",
    ]


def test_clinic_policy_cannot_replace_patient_cross_border_consent(monkeypatch):
    observed_external_flags = []

    class LocalOnly:
        def generate_chat_reply(self, *args, **kwargs):
            return {
                "_provider_source": "local_qwen",
                "reply": "Hangi şubenin konumunu istersiniz?",
                "confidence": 0.94,
                "intent": "ask_location",
                "requires_human_review": False,
                "data": {},
            }

    class ForbiddenOpenAI:
        def __init__(self):
            raise AssertionError("OpenAI must not be constructed without patient consent")

    settings = get_settings()
    monkeypatch.setattr(settings, "clinical_ai_enabled", True)
    monkeypatch.setattr(settings, "clinical_external_ai_allowed", True)
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(
        clinical_ai_service,
        "get_llm_provider",
        lambda _mode, external: observed_external_flags.append(external) or LocalOnly(),
    )
    monkeypatch.setattr(clinical_ai_service, "OpenAIProvider", ForbiddenOpenAI)
    clinic = SimpleNamespace(
        name="Test Klinik",
        default_language="tr",
        ai_auto_reply_threshold=0.9,
        emergency_disclaimer="Call emergency services.",
        organization_id=None,
        settings_json={
            "data_residency_mode": "hybrid_explicit_consent",
            "allow_cross_border_processors": True,
        },
    )

    result = clinical_ai_service.generate_clinical_reply(clinic, "Konumunuz nerede?")

    assert observed_external_flags == [False]
    assert result.data["provider_source"] == "local_qwen"
    assert result.data["external_ai_consent_verified"] is False


def _consent_test_clinic():
    """Sınır-ötesi işlemciye politika olarak İZİN VEREN klinik.

    Rıza kapısı testlerinde tek değişken hastanın rızası olsun diye klinik
    tarafındaki her kapı açık bırakılır.
    """
    return SimpleNamespace(
        name="Test Klinik",
        default_language="tr",
        ai_auto_reply_threshold=0.9,
        emergency_disclaimer="Call emergency services.",
        organization_id=None,
        settings_json={
            "data_residency_mode": "hybrid_explicit_consent",
            "allow_cross_border_processors": True,
        },
    )


def _arm_runtime_path(monkeypatch, *, cross_border: bool, calls: list):
    """`_try_runtime_reply` yolunu açar ve LLM çağrısını gözlemlenebilir yapar."""
    settings = get_settings()
    monkeypatch.setattr(settings, "clinical_ai_enabled", True)
    monkeypatch.setattr(settings, "clinical_external_ai_allowed", True)
    monkeypatch.setattr(
        clinical_ai_service, "runtime_is_cross_border", lambda: cross_border
    )

    def _spy_complete_json(**kwargs):
        calls.append(kwargs)
        return {
            "reply": "Merkez şubemiz Çankaya'da.",
            "confidence": 0.92,
            "intent": "ask_location",
            "action": "answer_location",
            "requires_human_review": False,
            "data": {},
        }

    monkeypatch.setattr(clinical_ai_service, "complete_json", _spy_complete_json)


def test_runtime_path_blocks_cross_border_llm_without_patient_consent(monkeypatch):
    """Klinik politikası hastanın açık rızasının yerine geçemez.

    Regresyon: `_try_runtime_reply` asıl sağlayıcı yolundan ÖNCE çalışıyor ve
    yalnızca klinik politikasına bakıyordu. Runtime OpenAI'a düştüğünde hasta
    metni rızasız yurt dışına çıkıyordu (KVKK md. 9 açık rıza ihlali).
    """
    calls: list = []
    _arm_runtime_path(monkeypatch, cross_border=True, calls=calls)

    result = clinical_ai_service.generate_clinical_reply(
        _consent_test_clinic(),
        "Konumunuz nerede?",
        external_ai_consent=False,
    )

    assert calls == [], "rıza yokken sınır-ötesi runtime'a istek gitmemeli"
    assert result.action != "collect_info" or result.data.get("provider_source") != "runtime"


def test_runtime_path_allows_cross_border_llm_with_patient_consent(monkeypatch):
    """Rıza VARSA aynı yol çalışmaya devam eder — kapı kilit değil, kapı."""
    calls: list = []
    _arm_runtime_path(monkeypatch, cross_border=True, calls=calls)

    clinical_ai_service.generate_clinical_reply(
        _consent_test_clinic(),
        "Konumunuz nerede?",
        external_ai_consent=True,
    )

    assert len(calls) == 1


def test_runtime_path_does_not_require_consent_for_local_runtime(monkeypatch):
    """Lokal runtime'da sınır-ötesi transfer YOK → rıza aranmaz.

    Yerel-öncelik davranışı korunmalı: rıza kapısını lokal işlemeye de
    uygulamak, KVKK'ya uygun olan yolu gereksiz yere kapatırdı.
    """
    calls: list = []
    _arm_runtime_path(monkeypatch, cross_border=False, calls=calls)

    clinical_ai_service.generate_clinical_reply(
        _consent_test_clinic(),
        "Konumunuz nerede?",
        external_ai_consent=False,
    )

    assert len(calls) == 1
