"""İP-2.7 — Yönetişim Zarfı adversarial test paketi (kapı-ihlali = 0).

150+ saldırgan senaryoda kapı-ihlali olmadığını; teşhis/sınır-ötesi/kimlik
sızıntısının sıfır olduğunu doğrular. Ayrıca noktalı-kimlik (`123.456.789.01`)
maskeleme sızıntısının kapatıldığını regresyon olarak kilitler.
"""

from __future__ import annotations

import pytest

from app.governance.adversarial import (
    build_corpus,
    evaluate_corpus,
    evaluate_scenario,
)
from app.services.clinical_compliance_service import mask_identifiers


@pytest.fixture(scope="module")
def report():
    return evaluate_corpus()


def test_corpus_has_at_least_150_scenarios():
    assert len(build_corpus()) >= 150


def test_zero_gate_violations(report):
    assert report.passed, f"Kapı ihlalleri: {report.violations}"
    assert report.violation_count == 0


def test_corpus_is_deterministic():
    assert build_corpus() == build_corpus()


@pytest.mark.parametrize("scenario", build_corpus(), ids=lambda s: s.category)
def test_each_scenario_passes(scenario):
    assert evaluate_scenario(scenario) == [], scenario.text


def test_every_category_covered(report):
    expected = {
        "pii_masking",
        "diagnosis_block",
        "emergency_escalation",
        "insurance_escalation",
        "identity_escalation",
        "residency_escalation",
        "health_recall",
    }
    assert expected <= set(report.per_category_total)


# ── Maskeleme sertleştirme regresyonları (kimlik sızıntısı) ──────────────────


@pytest.mark.parametrize(
    "raw",
    [
        "123.456.789.01",        # noktayla yazılmış kimlik (kapatılan sızıntı)
        "12345678901",           # bitişik TC
        "5412 3456 7890 1234",   # boşluklu kart
        "5412-3456-7890-1234",   # tireli kart
        "ayse@klinik.com",       # e-posta
        "+90 532 111 22 33",     # ülke kodlu telefon
        "(0532) 111 22 33",      # parantezli telefon
    ],
)
def test_identifier_formats_are_masked(raw):
    masked = mask_identifiers(f"hasta bilgisi {raw} kaydet")
    assert raw not in masked
    assert "[REDACTED]" in masked


@pytest.mark.parametrize(
    "benign",
    [
        "ücret 1500 TL ödedim",
        "randevu 14:30 da olsun",
        "5 diş 3 dolgu yapıldı",
        "rapor bölüm 1.4.2 ye bakın",
    ],
)
def test_benign_numbers_not_over_redacted(benign):
    # Para/saat/küçük sayı/kısa sürüm — maskelenmemeli (anlamlı içerik korunur).
    assert mask_identifiers(benign) == benign
