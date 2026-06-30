"""İP-2.6 — Yönetişim Zarfı kapı değişmezleri (property-based, enumeratif).

`hypothesis` bağımlılığı eklemeden, girdi uzayını deterministik biçimde tarayarak
(her ClinicIntent × her ikamet modu × harici-izin bayrağı × metin bataryası)
zarfın HER çıktısında geçerli olması gereken değişmezleri doğrular. Bu, kapı
mantığının ifadeye/duruma göre değil **yapısal** olarak garantili olduğunu
kanıtlar — İP-2 "kapı ihlal-edilemezliği" hedefinin temeli.

Saf import; `--noconftest` ile koşar (app.main zincirine değmez).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.governance.adversarial import (
    BLOCK_XBORDER_CONTROL,
    DOCTOR_APPROVAL_CONTROL,
    NO_DIAGNOSIS_CONTROL,
    XBORDER_CONSENT,
    _leaks_pii,
)
from app.models import ClinicIntent
from app.services.clinical_compliance_service import build_governance_context

RESIDENCY_MODES = ["tr_local_first", "eu_local", "hybrid_explicit_consent"]
EXTERNAL_FLAGS = [False, True]

# Değişmezlerin her koşulda tutması gereken metin bataryası (argo + PII + nötr).
TEXTS = [
    "dişim ağrıyor randevu istiyorum",
    "merhaba fiyat öğrenebilir miyim",
    "TC 12345678901 kaydedin",
    "numaram 0532 111 22 33",
    "sigorta provizyon sorgusu",
    "ağzımdan kan durmuyor acil",
    "teşhis koy hangi ilaç içeyim",
    "çalışma saatleriniz nedir",
    "123.456.789.01 noktalı kimlik",
    "ses kaydı arama metadata",
]


def _clinic(mode: str, external: bool):
    return SimpleNamespace(
        settings_json={"data_residency_mode": mode, "allow_cross_border_processors": external}
    )


def _all_contexts():
    """Tüm (intent × mod × harici × metin) kombinasyonlarını üretir."""
    for intent in ClinicIntent:
        for mode in RESIDENCY_MODES:
            for external in EXTERNAL_FLAGS:
                for text in TEXTS:
                    yield intent, mode, external, build_governance_context(
                        _clinic(mode, external), text, intent, "tr"
                    )


# Tüm kombinasyon sayısı (parametrize id'leri için) — büyük ama deterministik.
_CASES = list(_all_contexts())


@pytest.mark.parametrize("intent,mode,external,g", _CASES)
class TestUniversalInvariants:
    """Her zarf çıktısında geçerli olması gereken yapısal değişmezler."""

    def test_diagnosis_gate_always_present(self, intent, mode, external, g):
        # Teşhis sızıntısı = 0: zarf hiçbir koşulda teşhis/tedavi talimatına izin vermez.
        assert NO_DIAGNOSIS_CONTROL in g.required_controls

    def test_doctor_approval_control_always_present(self, intent, mode, external, g):
        assert DOCTOR_APPROVAL_CONTROL in g.required_controls

    def test_auto_send_iff_no_review_reasons(self, intent, mode, external, g):
        assert g.auto_send_allowed == (not g.human_review_reasons)

    def test_redacted_preview_never_leaks_pii(self, intent, mode, external, g):
        # Kimlik sızıntısı = 0: maskeli önizlemede ham PII kalmamalı.
        assert _leaks_pii(g.redacted_preview) == []

    def test_contact_data_always_classified(self, intent, mode, external, g):
        assert "contact_data" in g.data_classes
        assert g.data_classes == sorted(g.data_classes)

    def test_local_first_blocks_or_consents_cross_border(self, intent, mode, external, g):
        # Sınır-ötesi sızıntısı = 0: harici transfer kapalıysa engel kontrolü
        # bulunmalı ve sınır-ötesi rıza listelenmemeli.
        if not g.external_transfer_allowed:
            assert BLOCK_XBORDER_CONTROL in g.required_controls
            assert XBORDER_CONSENT not in g.consent_required_before
        else:
            assert XBORDER_CONSENT in g.consent_required_before


# ── Hedefe yönelik kapı değişmezleri (kombinasyondan bağımsız okunur) ─────────


@pytest.mark.parametrize("mode", RESIDENCY_MODES)
@pytest.mark.parametrize("external", EXTERNAL_FLAGS)
def test_emergency_never_auto_sends(mode, external):
    g = build_governance_context(
        _clinic(mode, external), "acil yardım kanama", ClinicIntent.MEDICAL_EMERGENCY, "tr"
    )
    assert g.auto_send_allowed is False
    assert g.sensitivity == "urgent_special_category"


@pytest.mark.parametrize("mode", RESIDENCY_MODES)
def test_insurance_never_auto_sends(mode):
    g = build_governance_context(
        _clinic(mode, False), "sgk provizyon", ClinicIntent.ASK_INSURANCE, "tr"
    )
    assert g.auto_send_allowed is False


def test_national_identifier_escalates_and_classified():
    g = build_governance_context(
        _clinic("tr_local_first", False), "TC 12345678901", ClinicIntent.BOOK_APPOINTMENT, "tr"
    )
    assert "national_identifier" in g.data_classes
    assert g.auto_send_allowed is False


def test_local_first_with_external_enabled_escalates():
    g = build_governance_context(
        _clinic("tr_local_first", True), "randevu", ClinicIntent.BOOK_APPOINTMENT, "tr"
    )
    assert g.auto_send_allowed is False
    assert "cross_border_processor_enabled_in_local_first_mode" in g.human_review_reasons


@pytest.mark.parametrize("intent", list(ClinicIntent))
def test_health_intents_classified_special_category(intent):
    from app.services.clinical_compliance_service import HEALTH_DATA_INTENTS

    g = build_governance_context(
        _clinic("tr_local_first", False), "nötr metin", intent, "tr"
    )
    if intent in HEALTH_DATA_INTENTS:
        assert "special_category_health_data" in g.data_classes
        assert "special_category_data_safeguards" in g.required_controls
        assert g.sensitivity != "standard"
