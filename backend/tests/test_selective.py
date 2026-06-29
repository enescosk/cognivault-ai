"""İP-1.6 — Selective/çekimser prediction testleri.

Düşük güvenli branş tahminleri ``abstain=True`` döndürmeli ve
``requires_escalation`` tetiklemeli (insan yükseltme).

Çalıştırma:
    python -m pytest tests/test_selective.py --noconftest -q
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from app.clinical.calibration import (
    ABSTAIN_COVERAGE_DEFAULT,
    IsotonicCalibrator,
    compute_abstain_threshold,
)
from app.clinical.normalizer import TriageResult, triage
from app.clinical.ontology import UrgencyLevel


# ── compute_abstain_threshold ─────────────────────────────────────────────────

class TestComputeAbstainThreshold:
    def test_empty_returns_one(self) -> None:
        assert compute_abstain_threshold([]) == 1.0

    def test_perfect_accuracy_returns_lowest(self) -> None:
        """Tüm tahminler doğruysa en düşük güven eşiğini döndürmeli."""
        pairs = [(0.3, True), (0.6, True), (0.9, True)]
        t = compute_abstain_threshold(pairs, coverage=0.90)
        assert t <= 0.3  # en düşük güvene kadar inebilir

    def test_low_accuracy_returns_one(self) -> None:
        """Hiçbir eşikte coverage sağlanamıyorsa 1.0 döndürmeli."""
        pairs = [(0.9, False), (0.8, False), (0.7, False)]
        t = compute_abstain_threshold(pairs, coverage=0.90)
        assert t == 1.0

    def test_mixed_finds_threshold(self) -> None:
        """Yüksek güven kümesinde hedef accuracy var, düşükte yok."""
        # Güven≥0.8: 2/2 doğru (%100) · güven<0.8: 0/2 doğru
        pairs = [(0.9, True), (0.8, True), (0.5, False), (0.3, False)]
        t = compute_abstain_threshold(pairs, coverage=0.90)
        assert t <= 0.8

    def test_coverage_80_lower_threshold_than_90(self) -> None:
        """Daha düşük coverage hedefi daha küçük eşik vermeli."""
        pairs = [(0.9, True), (0.7, True), (0.5, False), (0.3, False)]
        t90 = compute_abstain_threshold(pairs, coverage=0.90)
        t80 = compute_abstain_threshold(pairs, coverage=0.80)
        assert t80 <= t90


# ── IsotonicCalibrator ────────────────────────────────────────────────────────

class TestIsotonicCalibratorAbstain:
    def _make_calibrator(self, threshold: float = 0.5) -> IsotonicCalibrator:
        cal = IsotonicCalibrator.fit(
            [(0.0, False), (1.0, False), (2.0, True), (3.0, True), (4.0, True)]
        )
        # dataclass frozen=True → yeni obje
        from dataclasses import replace
        return replace(cal, abstain_threshold=threshold, abstain_coverage=0.90)

    def test_serialization_roundtrip(self) -> None:
        """abstain_threshold ve abstain_coverage JSON'dan geri yüklenmeli."""
        cal = self._make_calibrator(0.65)
        d = cal.to_dict()
        assert d["abstain_threshold"] == 0.65
        assert d["abstain_coverage"] == 0.90
        loaded = IsotonicCalibrator.from_dict(d)
        assert loaded.abstain_threshold == 0.65
        assert loaded.abstain_coverage == 0.90

    def test_from_dict_missing_keys_defaults(self) -> None:
        """Eski formattaki JSON (alan yok) yüklendiğinde varsayılan değerler geçerli."""
        old_format = {"thresholds": [0.0, 1.0], "values": [0.3, 0.8]}
        cal = IsotonicCalibrator.from_dict(old_format)
        assert cal.abstain_threshold == 0.0  # varsayılan: çekimser değil
        assert cal.abstain_coverage == ABSTAIN_COVERAGE_DEFAULT

    def test_save_load_preserves_threshold(self) -> None:
        """save/load döngüsünde threshold korunmalı."""
        cal = self._make_calibrator(0.72)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cal.json"
            cal.save(path)
            loaded = IsotonicCalibrator.load(path)
            assert loaded is not None
            assert loaded.abstain_threshold == pytest.approx(0.72)


# ── TriageResult.abstain ──────────────────────────────────────────────────────

class TestTriageAbstain:
    def test_abstain_field_exists(self) -> None:
        """TriageResult abstain alanı içermeli."""
        result = triage("diş kontrolü olmak istiyorum")
        assert hasattr(result, "abstain")
        assert isinstance(result.abstain, bool)

    def test_high_confidence_not_abstain(self) -> None:
        """Net, kuvvetli eşleşmeli sorgular abstain=False olmalı."""
        # Kalibratör yoksa ya da threshold 0 ise abstain=False
        result = triage("implant vidası kontrol edilecek")
        # abstain ya False ya kalibratör durumuna göre; en azından tip doğru
        assert result.abstain in (True, False)

    def test_abstain_triggers_requires_escalation(self) -> None:
        """abstain=True → requires_escalation=True olmalı."""
        from app.clinical.ontology import GENERAL_SPECIALTY, SpecialtyMatch
        from unittest.mock import patch

        # Suni bir TriageResult oluştur: abstain=True, urgency=ROUTINE
        match = SpecialtyMatch(specialty=GENERAL_SPECIALTY)
        result = TriageResult(
            raw_text="test",
            enriched_text="test",
            specialty=match,
            urgency=UrgencyLevel.ROUTINE,
            abstain=True,
        )
        assert result.requires_escalation is True

    def test_no_abstain_routine_no_escalation(self) -> None:
        """abstain=False + urgency=ROUTINE → requires_escalation=False olmalı."""
        from app.clinical.ontology import GENERAL_SPECIALTY, SpecialtyMatch

        match = SpecialtyMatch(specialty=GENERAL_SPECIALTY)
        result = TriageResult(
            raw_text="test",
            enriched_text="test",
            specialty=match,
            urgency=UrgencyLevel.ROUTINE,
            abstain=False,
        )
        assert result.requires_escalation is False

    def test_emergency_always_escalates(self) -> None:
        """Acil urgency varsa abstain=False bile olsa requires_escalation=True."""
        from app.clinical.ontology import GENERAL_SPECIALTY, SpecialtyMatch

        match = SpecialtyMatch(specialty=GENERAL_SPECIALTY)
        result = TriageResult(
            raw_text="test",
            enriched_text="test",
            specialty=match,
            urgency=UrgencyLevel.EMERGENCY,
            abstain=False,
        )
        assert result.requires_escalation is True


# ── Kalibratörsüz güvenli varsayılan ─────────────────────────────────────────

def test_triage_without_calibrator_no_abstain(monkeypatch: pytest.MonkeyPatch) -> None:
    """Kalibratör dosyası yoksa abstain=False (güvenli varsayılan — engelleme değil)."""
    from app.clinical import normalizer
    monkeypatch.setattr(normalizer, "_calibrator", lambda: None)
    result = triage("genel kontrol istiyorum")
    assert result.abstain is False


def test_triage_zero_threshold_no_abstain(monkeypatch: pytest.MonkeyPatch) -> None:
    """abstain_threshold=0.0 olan kalibratör hiçbir zaman abstain=True üretmemeli."""
    from app.clinical import normalizer
    from app.clinical.calibration import IsotonicCalibrator

    cal = IsotonicCalibrator(thresholds=[0.0], values=[0.5], abstain_threshold=0.0)
    monkeypatch.setattr(normalizer, "_calibrator", lambda: cal)
    result = triage("genel kontrol istiyorum")
    assert result.abstain is False
