"""Semptom/acil triyajının harici işlemciye (OpenAI) sızıntı yapmadığını kilitler.

`build_compliance_profile` (clinical_compliance_service.py) "openai" işlemcisini
`clinical_external_ai_allowed AND allow_cross_border_processors` ikisi de açık
olmadan "blocked" olarak tanımlar. `assess_medical_triage`/`_try_openai_triage`
bu iki bayrağı da (artı klinik-seviyesi sınır-ötesi rızayı) uygulamak zorunda —
aksi halde ham semptom metni (özel-nitelikli sağlık verisi) maskelenmeden dışarı
çıkar. Bu dosya o kapıyı ve PII maskelemesini regresyona karşı kilitler.
"""

import json
from types import SimpleNamespace

from app.models import Clinic
from app.services import medical_triage_service as svc


def _settings(**overrides):
    base = dict(
        clinical_ai_enabled=False,
        clinical_external_ai_allowed=False,
        openai_api_key="sk-test-key",
        openai_model="gpt-4o-mini",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _clinic(allow_cross_border: bool = False) -> Clinic:
    return Clinic(
        name="Test Clinic",
        slug="test-clinic-triage",
        default_language="tr",
        settings_json={"allow_cross_border_processors": allow_cross_border},
    )


class _FakeOpenAI:
    """OpenAI istemcisini taklit eder; gerçek ağ çağrısı yapmaz, gönderileni kaydeder."""

    captured_calls: list[dict] = []

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        _FakeOpenAI.captured_calls.append(kwargs)
        payload = {
            "urgency": "same_day",
            "red_flags": [],
            "possible_conditions": [],
            "recommended_action": "test",
            "patient_safe_reply": "test",
            "doctor_summary": "test",
            "follow_up_questions": [],
            "safety_disclaimer": "test",
            "requires_doctor_review": True,
        }
        message = SimpleNamespace(content=json.dumps(payload))
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


SYMPTOM_TEXT = "dişim çok ağrıyor, numaram 05551234567, TC 12345678901"


def test_default_settings_block_external_triage(monkeypatch):
    monkeypatch.setattr(svc, "get_settings", lambda: _settings())
    clinic = _clinic(allow_cross_border=True)
    assert svc._try_openai_triage(clinic, SYMPTOM_TEXT, "tr") is None


def test_clinical_ai_enabled_alone_is_not_sufficient(monkeypatch):
    # clinical_ai_enabled=True ama clinical_external_ai_allowed=False → hâlâ engellenmeli.
    monkeypatch.setattr(svc, "get_settings", lambda: _settings(clinical_ai_enabled=True))
    clinic = _clinic(allow_cross_border=True)
    assert svc._try_openai_triage(clinic, SYMPTOM_TEXT, "tr") is None


def test_missing_clinic_level_consent_blocks_external_triage(monkeypatch):
    # Uygulama bayrakları açık ama klinik sınır-ötesi rıza vermemiş → hâlâ engellenmeli.
    monkeypatch.setattr(
        svc,
        "get_settings",
        lambda: _settings(clinical_ai_enabled=True, clinical_external_ai_allowed=True),
    )
    clinic = _clinic(allow_cross_border=False)
    assert svc._try_openai_triage(clinic, SYMPTOM_TEXT, "tr") is None


def test_missing_api_key_blocks_external_triage(monkeypatch):
    monkeypatch.setattr(
        svc,
        "get_settings",
        lambda: _settings(
            clinical_ai_enabled=True, clinical_external_ai_allowed=True, openai_api_key=""
        ),
    )
    clinic = _clinic(allow_cross_border=True)
    assert svc._try_openai_triage(clinic, SYMPTOM_TEXT, "tr") is None


def test_fully_consented_path_masks_pii_before_external_call(monkeypatch):
    monkeypatch.setattr(
        svc,
        "get_settings",
        lambda: _settings(clinical_ai_enabled=True, clinical_external_ai_allowed=True),
    )
    monkeypatch.setattr(svc, "OpenAI", _FakeOpenAI)
    _FakeOpenAI.captured_calls = []
    clinic = _clinic(allow_cross_border=True)

    result = svc._try_openai_triage(clinic, SYMPTOM_TEXT, "tr")

    assert result is not None
    assert result.source == "openai_structured"
    assert len(_FakeOpenAI.captured_calls) == 1
    sent_prompt = _FakeOpenAI.captured_calls[0]["messages"][1]["content"]
    assert "05551234567" not in sent_prompt
    assert "12345678901" not in sent_prompt
    assert "[REDACTED]" in sent_prompt


def test_assess_medical_triage_falls_back_to_rules_when_blocked(monkeypatch):
    monkeypatch.setattr(svc, "get_settings", lambda: _settings())
    clinic = _clinic(allow_cross_border=True)
    assessment = svc.assess_medical_triage(clinic, SYMPTOM_TEXT, "tr")
    assert assessment.source == "rules"
