"""İP-1.2 korpus testleri.

Doğrular:
- dental_tr.jsonl ≥500 anonim senaryo (iş planı başarı ölçütü).
- Her kayıt şema + ontoloji açısından geçerli; PII sızıntısı yok.
- Tüm branşlar ve üç aciliyet seviyesi temsil ediliyor.
- Üretici, commit'lenmiş dosyayla senkron (yeniden üretim aynı sonucu verir).
- Golden set geçerli ve zorluk açısından kapsamlı.
"""

from __future__ import annotations

import pytest

from app.clinical.corpus import load_corpus, scan_pii, validate_entry
from app.clinical.corpus.build import MIN_TOTAL, build_corpus
from app.clinical.corpus.build_golden import build_golden
from app.clinical.corpus.schema import corpus_data_dir
from app.clinical.ontology import SPECIALTY_BY_CODE, UrgencyLevel


@pytest.fixture(scope="module")
def dental_corpus():
    return load_corpus(corpus_data_dir() / "dental_tr.jsonl")


@pytest.fixture(scope="module")
def golden_corpus():
    return load_corpus(corpus_data_dir() / "golden.jsonl")


# ─────────────────────────────────────────────────────────────────────────────
# Sentetik korpus (dental_tr.jsonl)
# ─────────────────────────────────────────────────────────────────────────────

def test_corpus_meets_minimum_size(dental_corpus):
    assert len(dental_corpus) >= MIN_TOTAL


def test_every_entry_is_valid(dental_corpus):
    for entry in dental_corpus:
        assert validate_entry(entry) == [], f"{entry.id}: {validate_entry(entry)}"


def test_no_pii_leak(dental_corpus):
    for entry in dental_corpus:
        assert scan_pii(entry.text) == [], f"{entry.id} PII içeriyor: {entry.text!r}"


def test_ids_are_unique(dental_corpus):
    ids = [entry.id for entry in dental_corpus]
    assert len(ids) == len(set(ids))


def test_all_specialties_represented(dental_corpus):
    seen = {entry.specialty_code for entry in dental_corpus}
    assert seen == set(SPECIALTY_BY_CODE)


def test_all_urgency_levels_represented(dental_corpus):
    seen = {entry.urgency for entry in dental_corpus}
    assert seen == {level.value for level in UrgencyLevel}


def test_emergency_entries_exist(dental_corpus):
    emergencies = [e for e in dental_corpus if e.urgency == UrgencyLevel.EMERGENCY.value]
    assert len(emergencies) >= 20


def test_texts_are_unique(dental_corpus):
    from app.clinical.ontology import normalize_tr

    norms = [normalize_tr(e.text) for e in dental_corpus]
    assert len(norms) == len(set(norms)), "korpusta tekrar eden metin var"


def test_committed_file_matches_generator(dental_corpus):
    """Diskteki dosya, üreticinin çıktısıyla birebir aynı olmalı (drift kapısı)."""
    regenerated = build_corpus()
    assert dental_corpus == regenerated, (
        "dental_tr.jsonl üreticiyle senkron değil — "
        "`python -m app.clinical.corpus.build` ile yeniden üretin."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Golden değerlendirme seti (golden.jsonl)
# ─────────────────────────────────────────────────────────────────────────────

def test_golden_loads_and_is_valid(golden_corpus):
    assert len(golden_corpus) >= 30
    for entry in golden_corpus:
        assert validate_entry(entry) == [], f"{entry.id}: {validate_entry(entry)}"
        assert entry.source == "golden_curated"


def test_golden_covers_all_urgency_levels(golden_corpus):
    seen = {entry.urgency for entry in golden_corpus}
    assert seen == {level.value for level in UrgencyLevel}


def test_golden_no_pii(golden_corpus):
    for entry in golden_corpus:
        assert scan_pii(entry.text) == [], f"{entry.id} PII içeriyor"


def test_golden_matches_generator(golden_corpus):
    assert golden_corpus == build_golden()
