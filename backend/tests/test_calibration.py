"""İP-1.5 — güven kalibrasyonu testleri.

Kapsam: ECE metriği, isotonic (PAV) regresyon değişmezleri, JSON kalıcılığı,
ham güven sinyali ve korpusta kabul ölçütü (ECE < 0,05) + triyaj entegrasyonu.
"""

from __future__ import annotations

from app.clinical.calibrate import ECE_TARGET, build_pairs, split
from app.clinical.calibration import (
    IsotonicCalibrator,
    expected_calibration_error,
    raw_confidence_signal,
)
from app.clinical.normalizer import triage

# ── ECE metriği ──────────────────────────────────────────────────────────────


def test_ece_zero_when_confidence_matches_accuracy():
    # Güven 0.9 ve gerçekte %90 doğru → kalibrasyon hatası yok.
    pairs = [(0.9, True)] * 9 + [(0.9, False)]
    assert expected_calibration_error(pairs) < 0.01


def test_ece_high_when_overconfident():
    # Güven ~1.0 ama hepsi yanlış → ECE neredeyse 1.0.
    pairs = [(0.99, False)] * 50
    assert expected_calibration_error(pairs) > 0.95


def test_ece_empty_is_zero():
    assert expected_calibration_error([]) == 0.0


# ── Isotonic regresyon (Pool-Adjacent-Violators) ─────────────────────────────


def test_isotonic_values_are_monotonic_nondecreasing():
    pairs = [(0.0, False), (1.0, True), (2.0, False), (3.0, True), (4.0, True)]
    cal = IsotonicCalibrator.fit(pairs)
    assert cal.values == sorted(cal.values)


def test_isotonic_pools_violators_and_stays_monotonic():
    # raw=3 (yanlış) raw=2 (doğru) ardından gelir → ihlal; PAV havuzlamalı.
    pairs = (
        [(1.0, True)] * 10
        + [(2.0, True)] * 10
        + [(3.0, False)] * 10
        + [(4.0, True)] * 10
    )
    cal = IsotonicCalibrator.fit(pairs)
    assert cal.values == sorted(cal.values)
    # Daha yüksek ham skor, daha düşük kalibre güven veremez.
    assert cal.predict_one(3.0) >= cal.predict_one(1.0) - 1e-9
    assert cal.predict_one(4.0) >= cal.predict_one(3.0) - 1e-9


def test_isotonic_predict_clamps_below_first_threshold():
    cal = IsotonicCalibrator.fit([(5.0, True), (10.0, True)])
    assert cal.predict_one(-3.0) == cal.values[0]


def test_isotonic_outputs_are_probabilities():
    cal = IsotonicCalibrator.fit([(0.0, False), (1.0, False), (2.0, True), (3.0, True)])
    assert all(0.0 <= v <= 1.0 for v in cal.values)


# ── JSON kalıcılığı ──────────────────────────────────────────────────────────


def test_calibrator_json_roundtrip(tmp_path):
    cal = IsotonicCalibrator.fit([(0.0, False), (1.0, True), (2.0, True), (3.0, True)])
    path = tmp_path / "calibration.json"
    cal.save(path)
    loaded = IsotonicCalibrator.load(path)
    assert loaded is not None
    for raw in (-2.0, 0.0, 0.5, 1.0, 2.5, 3.0, 9.0):
        assert loaded.predict_one(raw) == cal.predict_one(raw)


def test_load_missing_artifact_returns_none(tmp_path):
    assert IsotonicCalibrator.load(tmp_path / "yok.json") is None


# ── Ham güven sinyali ────────────────────────────────────────────────────────


def test_raw_signal_zero_when_no_specialty_keyword():
    assert raw_confidence_signal("merhaba bir randevu almak istiyorum") == 0.0


def test_raw_signal_positive_for_clear_complaint():
    # Üretimde sinyal zenginleştirilmiş metin üzerinden hesaplanır (triage),
    # böylece "apse" gibi argo terimler önce kanonik forma genişletilir.
    assert triage("dişimde apse var şişti çok ağrıyor").raw_confidence > 0.0


# ── İP-1.5 KABUL ÖLÇÜTÜ: korpusta kalibre ECE < 0,05 ─────────────────────────


def test_calibrated_ece_below_target_on_corpus():
    """İş planı başarı ölçütü: ≥500 senaryoluk sentetik sette ECE < 0,05."""
    pairs = build_pairs("dental_tr.jsonl")
    train, test = split(pairs)
    calibrator = IsotonicCalibrator.fit(train)
    calibrated = [(calibrator.predict_one(raw), ok) for raw, ok in test]
    assert expected_calibration_error(calibrated) < ECE_TARGET


# ── Triyaj entegrasyonu ──────────────────────────────────────────────────────


def test_triage_exposes_calibrated_confidence():
    result = triage("dişimde apse var çok ağrıyor")
    assert result.raw_confidence > 0.0
    assert 0.0 <= result.confidence <= 1.0
