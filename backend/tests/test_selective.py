"""İP-1.6 — çekimser tahmin (selective prediction) testleri.

Kapsam: kabul/çekimser kararı ve gerekçeleri (no-evidence / ambiguous /
low-confidence), aciliyetle birleşik insan-yükseltme, konformal eşik seçimi
(fit_threshold) değişmezleri, risk-kapsam metrikleri, eşik artefaktı kalıcılığı
ve golden sette selektif-doğruluk kazancı.
"""

from __future__ import annotations

from app.clinical.corpus.schema import corpus_data_dir, load_corpus
from app.clinical.selective import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    AbstainReason,
    SelectiveMetrics,
    decide,
    evaluate_selective,
    fit_threshold,
    load_threshold,
    save_threshold,
)

# ── Kabul / çekimser kararı ──────────────────────────────────────────────────


def test_accepts_clear_single_specialty():
    d = decide("dişimde dolgu düştü", threshold=0.5)
    assert d.accepted
    assert d.specialty_code == "restoratif"
    assert d.abstain_reasons == ()
    assert not d.escalate_to_human


def test_abstains_on_no_evidence():
    # Anahtar-kelimesiz genel şikâyet → genel diş'e düşüş → insana yükselt.
    d = decide("merhaba bir randevu almak istiyorum", threshold=0.5)
    assert not d.accepted
    assert d.specialty_code == "genel_dis"
    assert AbstainReason.NO_EVIDENCE.value in d.abstain_reasons
    assert d.escalate_to_human


def test_abstains_on_ambiguous_evidence():
    # İki branş eşit skorla yarışıyor → çelişkili kanıt → çekimser kal.
    d = decide("dolgu ve implant", threshold=0.5)
    assert not d.accepted
    assert AbstainReason.AMBIGUOUS_EVIDENCE.value in d.abstain_reasons


def test_abstains_on_low_confidence():
    # Tek zayıf eşleşme; eşik kalibre güvenin üstünde → düşük-güven çekimseri.
    d = decide("dişlerimi beyazlatmak istiyorum", threshold=0.99)
    assert not d.accepted
    assert AbstainReason.LOW_CONFIDENCE.value in d.abstain_reasons
    # Kanıt var (estetik branşı eşleşti); tek gerekçe düşük güven olmalı.
    assert AbstainReason.NO_EVIDENCE.value not in d.abstain_reasons


def test_low_threshold_accepts_same_case():
    # Aynı şikâyet, eşik kalibre güvenin altında → kabul.
    d = decide("dişlerimi beyazlatmak istiyorum", threshold=0.5)
    assert d.accepted
    assert d.specialty_code == "estetik_dis"


# ── Aciliyetle birleşik insan-yükseltme ──────────────────────────────────────


def test_emergency_escalates_even_when_specialty_accepted():
    # Branş güvenle eşleşse bile acil sinyali insana yükseltmeyi zorlar.
    d = decide("implantım var ama nefes alamıyorum", threshold=0.5)
    assert d.triage.requires_escalation  # aciliyet yolu
    assert d.escalate_to_human


# ── Konformal eşik seçimi (fit_threshold) ────────────────────────────────────


def test_fit_threshold_meets_target_risk():
    # %5 hatalı, %95 doğru, hepsi aynı güvende → o güveni eşik seç (risk=hedef).
    pairs = [(0.9, True)] * 19 + [(0.9, False)]
    assert fit_threshold(pairs, target_risk=0.05) == 0.9


def test_fit_threshold_excludes_risky_low_confidence():
    # Düşük güvenli örnekler hatalı → eşik onları dışlayacak kadar yükselir.
    pairs = [(0.2, False)] * 10 + [(0.9, True)] * 10
    assert fit_threshold(pairs, target_risk=0.05) == 0.9


def test_fit_threshold_rejects_all_when_unachievable():
    # Hiçbir alt küme riski sağlamıyor → tüm güvenlerin üstünde eşik (hepsini reddet).
    pairs = [(0.9, False)] * 10
    assert fit_threshold(pairs, target_risk=0.05) > 0.9


def test_fit_threshold_empty_returns_default():
    assert fit_threshold([], target_risk=0.05) == DEFAULT_CONFIDENCE_THRESHOLD


# ── Risk-kapsam metrikleri ───────────────────────────────────────────────────


def test_selective_metrics_properties():
    m = SelectiveMetrics(total=10, accepted=8, accepted_correct=6)
    assert m.coverage == 0.8
    assert m.selective_accuracy == 0.75
    assert m.selective_risk == 0.25
    assert m.abstained == 2


def test_selective_metrics_empty_accept_is_safe():
    # Hiç kabul yoksa selektif doğruluk 1.0 (tanımsız değil) — güvenli varsayılan.
    m = SelectiveMetrics(total=5, accepted=0, accepted_correct=0)
    assert m.coverage == 0.0
    assert m.selective_accuracy == 1.0


def test_evaluate_selective_counts_accepted_correct():
    items = [
        ("dişimde dolgu düştü", "restoratif"),       # kabul + doğru
        ("merhaba randevu istiyorum", "genel_dis"),  # çekimser (no-evidence)
    ]
    m = evaluate_selective(items, threshold=0.5)
    assert m.total == 2
    assert m.accepted == 1
    assert m.accepted_correct == 1
    assert m.coverage == 0.5


# ── Eşik artefaktı kalıcılığı ────────────────────────────────────────────────


def test_threshold_save_load_roundtrip(tmp_path):
    path = tmp_path / "selective.json"
    save_threshold(0.73, 0.05, path=path)
    assert load_threshold(path) == 0.73


def test_load_threshold_missing_returns_default(tmp_path):
    assert load_threshold(tmp_path / "yok.json") == DEFAULT_CONFIDENCE_THRESHOLD


# ── Golden sette selektif-doğruluk kazancı (İP-1.6 kabul ölçütü) ──────────────


def test_selective_layer_improves_golden_accuracy():
    """Çekimser katman, golden sette KABUL edilen tahminlerde doğruluğu
    ham doğruluğun belirgin üstüne çıkarmalı (kanıtsız kaçışları yükselterek).
    """
    items = [(e.text, e.specialty_code) for e in load_corpus(corpus_data_dir() / "golden.jsonl")]
    threshold = load_threshold()  # üretim eşiği
    m = evaluate_selective(items, threshold=threshold)
    base_accuracy = 22 / 35  # ≈ %62,9 ham doğruluk (İP-1.5 raporu)
    assert m.selective_accuracy > base_accuracy + 0.10  # en az 10 puan kazanç
    assert m.abstained > 0  # gerçekten çekimser kaldı
