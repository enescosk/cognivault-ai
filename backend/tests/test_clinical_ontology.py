"""İP-1.1 — Branş + aciliyet ontolojisi davranış testleri.

Ontoloji, triyaj yönlendiricisinin (İP-1.4) ve kalibrasyonun (İP-1.5)
temelidir; bu testler şemanın sözleşmesini (kanonik adlar, kod kararlılığı,
aciliyet sıralaması, varsayılana düşme) kilitler.
"""

from __future__ import annotations

import pytest

from app.clinical.ontology import (
    GENERAL_SPECIALTY,
    SPECIALTY_BY_CODE,
    SPECIALTY_REGISTRY,
    UrgencyLevel,
    assess_urgency,
    match_specialty,
    normalize_tr,
)


def test_normalize_tr_strips_turkish_accents():
    assert normalize_tr("Dişim ÇÖK Ağrıyor") == "disim cok agriyor"


@pytest.mark.parametrize(
    "text,expected_code",
    [
        ("dolgum düştü", "restoratif"),
        ("dişim zonkluyor gece ağrısı var", "endodonti"),
        ("diş etim kanıyor", "periodontoloji"),
        ("çocuğumun süt dişi", "pedodonti"),
        ("braket taktırmak istiyorum", "ortodonti"),
        ("implant kontrolü", "implantoloji"),
        ("20lik dişimi çektireceğim", "cene_cerrahisi"),
        ("diş beyazlatma", "estetik_dis"),
    ],
)
def test_match_specialty_routes_known_complaints(text, expected_code):
    assert match_specialty(text).specialty.code == expected_code


def test_match_specialty_falls_back_to_general():
    result = match_specialty("merhaba bir bilgi almak istiyorum")
    assert result.is_default
    assert result.specialty is GENERAL_SPECIALTY


def test_match_specialty_reports_matched_keywords():
    result = match_specialty("implant vidası gevşedi")
    assert not result.is_default
    assert "implant" in result.matched_keywords


@pytest.mark.parametrize(
    "text,expected",
    [
        ("rutin kontrol randevusu", UrgencyLevel.ROUTINE),
        ("dişim ağrıyor zonkluyor", UrgencyLevel.PRIORITY),
        ("nefes alamıyorum yüzüm şişti", UrgencyLevel.EMERGENCY),
        ("112 acil çene kırığı", UrgencyLevel.EMERGENCY),
    ],
)
def test_assess_urgency_levels(text, expected):
    assert assess_urgency(text) == expected


def test_emergency_outranks_priority():
    # Hem priority hem emergency işareti varsa emergency kazanmalı.
    assert assess_urgency("dişim ağrıyor ama nefes alamıyorum") == UrgencyLevel.EMERGENCY


def test_urgency_rank_is_ordered():
    assert (
        UrgencyLevel.ROUTINE.rank
        < UrgencyLevel.PRIORITY.rank
        < UrgencyLevel.EMERGENCY.rank
    )


def test_urgency_escalation_flags():
    assert UrgencyLevel.EMERGENCY.requires_human_escalation
    assert UrgencyLevel.PRIORITY.requires_human_escalation
    assert not UrgencyLevel.ROUTINE.requires_human_escalation


def test_urgency_values_preserve_legacy_strings():
    # Aşağı akış string karşılaştırmaları kırılmamalı.
    assert UrgencyLevel.ROUTINE.value == "routine"
    assert UrgencyLevel.PRIORITY.value == "priority"
    assert UrgencyLevel.EMERGENCY.value == "emergency"


def test_specialty_codes_are_unique_and_indexed():
    codes = [spec.code for spec in SPECIALTY_REGISTRY]
    assert len(codes) == len(set(codes)), "branş kodları benzersiz olmalı"
    for spec in SPECIALTY_REGISTRY:
        assert SPECIALTY_BY_CODE[spec.code] is spec
    assert SPECIALTY_BY_CODE[GENERAL_SPECIALTY.code] is GENERAL_SPECIALTY
