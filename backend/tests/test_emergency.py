"""İP-1.7 — acil-recall kapsama testleri (kaçan acil ≈ 0).

Kapsam: adversarial acil senaryolarının tamamının EMERGENCY tespit edilmesi
(recall = %100), acile-benzeyen tuzakların acile kaçmaması (precision koruması),
bare "nefes" yanlış-pozitif regresyonu ve korpus-genel recall kapısı.
"""

from __future__ import annotations

import pytest

from app.clinical.corpus.build_emergency import EMERGENCY_CASES, HARD_NEGATIVES
from app.clinical.corpus.schema import corpus_data_dir, load_corpus
from app.clinical.emergency_report import CORPUS_FILES, evaluate_recall
from app.clinical.normalizer import triage
from app.clinical.ontology import UrgencyLevel, assess_urgency


# ── Adversarial acillerin tamamı yakalanmalı (recall) ────────────────────────


@pytest.mark.parametrize("text", [c[0] for c in EMERGENCY_CASES])
def test_adversarial_emergency_detected(text):
    assert triage(text).urgency == UrgencyLevel.EMERGENCY, (
        f"KAÇAN ACİL: {text!r} → {triage(text).urgency.value}"
    )


# ── Acile-benzeyen tuzaklar acile kaçmamalı (precision) ──────────────────────


@pytest.mark.parametrize("text,urgency", [(c[0], c[2]) for c in HARD_NEGATIVES])
def test_hard_negatives_not_emergency(text, urgency):
    assert triage(text).urgency != UrgencyLevel.EMERGENCY, (
        f"YANLIŞ-POZİTİF: {text!r} (etiket {urgency}) → acil sanıldı"
    )


# ── Bare "nefes" regresyonu — halitozis acil olmamalı ────────────────────────


def test_halitosis_not_emergency():
    # "nefesim kokuyor" (ağız kokusu) rutindir; bare "nefes" anahtarı
    # kaldırıldığı için artık acile çıkmamalı.
    assert triage("nefesim kötü kokuyor ağız kokusu var").urgency != UrgencyLevel.EMERGENCY
    assert assess_urgency("nefesim kötü kokuyor") != UrgencyLevel.EMERGENCY


def test_airway_phrase_still_emergency():
    # Gerçek havayolu güçlüğü hâlâ acil olmalı.
    assert assess_urgency("nefes alamıyorum") == UrgencyLevel.EMERGENCY
    assert triage("soluk alamıyorum yüzüm şişti").urgency == UrgencyLevel.EMERGENCY


# ── Korpus-genel recall kapısı (İP-1.7 kabul ölçütü) ─────────────────────────


def test_corpus_emergency_recall_is_total():
    """Tüm korpus dosyalarında kaçan acil = 0 (recall = %100)."""
    missed: list[str] = []
    total_emergencies = 0
    for fname in CORPUS_FILES:
        report = evaluate_recall(load_corpus(corpus_data_dir() / fname), fname)
        total_emergencies += report.emergencies
        missed.extend(m.text for m in report.missed)
    assert total_emergencies >= 70  # anlamlı bir acil kütlesi ölçülüyor
    assert missed == [], f"kaçan acil(ler): {missed}"


def test_corpus_no_false_positive_emergency():
    """Rutin/öncelik etiketli hiçbir vaka acile kaçmamalı."""
    false_positives: list[str] = []
    for fname in CORPUS_FILES:
        report = evaluate_recall(load_corpus(corpus_data_dir() / fname), fname)
        if report.false_positives:
            false_positives.append(f"{fname}: {report.false_positives}")
    assert false_positives == [], f"acile-kaçan yanlış-pozitif: {false_positives}"
