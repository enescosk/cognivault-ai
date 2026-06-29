"""İP-1.7 — Acil-recall garantisi: adversarial acil korpusu kapsama testi.

%100 recall hedefi: triage() ve extract_clinical_intake() servis yolu
emergency_adversarial.jsonl dosyasındaki HİÇBİR acil senaryoyu kaçırmamalı.

Çalıştırma:
    python -m pytest tests/test_emergency.py --noconftest -q
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.clinical.normalizer import triage
from app.services.clinical_ai_service import extract_clinical_intake

_CORPUS_PATH = (
    Path(__file__).resolve().parent.parent
    / "app/clinical/corpus/data/emergency_adversarial.jsonl"
)


def _load_adversarial() -> list[tuple[str, str]]:
    """(case_id, text) döndürür; yalnız urgency=emergency olanlar."""
    cases: list[tuple[str, str]] = []
    for line in _CORPUS_PATH.read_text(encoding="utf-8").strip().splitlines():
        obj = json.loads(line)
        if obj.get("urgency") == "emergency":
            cases.append((obj["id"], obj["text"]))
    return cases


_CASES = _load_adversarial()


# ── triage() yolu ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("case_id,text", _CASES, ids=[c[0] for c in _CASES])
def test_triage_emergency_recall(case_id: str, text: str) -> None:
    """triage() İP-1 motoru adversarial acil senaryolarını kaçırmamalı.

    Recall hedefi: %100 (sıfır kaçan acil).
    """
    result = triage(text)
    assert result.urgency.value == "emergency", (
        f"[{case_id}] triage() → {result.urgency.value!r}; beklenen 'emergency'.\n"
        f"  Metin:   {text!r}\n"
        f"  Zengin:  {result.enriched_text!r}\n"
        f"  Genişl.: {result.expansions}"
    )


# ── extract_clinical_intake() servis yolu ─────────────────────────────────────

@pytest.mark.parametrize("case_id,text", _CASES, ids=[c[0] for c in _CASES])
def test_service_path_emergency_recall(case_id: str, text: str) -> None:
    """extract_clinical_intake() servis yolu adversarial acil senaryolarını kaçırmamalı.

    İP-1 motorundan bağımsız bir servis override'ı olmadığında bu test,
    triage() motorunun aynı recall'ı servis katmanına taşıdığını kanıtlar.
    """
    intake = extract_clinical_intake(text)
    assert intake["urgency"] == "emergency", (
        f"[{case_id}] intake['urgency'] → {intake['urgency']!r}; beklenen 'emergency'.\n"
        f"  Metin: {text!r}"
    )


# ── Corpus sağlık kontrolleri ─────────────────────────────────────────────────

def test_adversarial_corpus_exists() -> None:
    """Adversarial acil korpusu mevcut olmalı."""
    assert _CORPUS_PATH.exists(), f"Corpus bulunamadı: {_CORPUS_PATH}"


def test_adversarial_corpus_non_empty() -> None:
    """Corpus en az 30 acil senaryo içermeli."""
    assert len(_CASES) >= 30, f"Yeterli senaryo yok: {len(_CASES)}"


def test_adversarial_corpus_all_emergency() -> None:
    """Dosyadaki tüm satırların urgency=emergency olduğunu doğrula."""
    for line in _CORPUS_PATH.read_text(encoding="utf-8").strip().splitlines():
        obj = json.loads(line)
        assert obj.get("urgency") == "emergency", (
            f"Adversarial korpusta emergency-dışı satır: {obj['id']}"
        )


def test_adversarial_ids_unique() -> None:
    """Tüm ID'ler benzersiz olmalı."""
    ids = [c[0] for c in _CASES]
    assert len(ids) == len(set(ids)), "Çakışan ID'ler var"
