"""İP-4.3 — Otomatik-yanıt eşiği öğrenme testleri (saf-import, DB gerektirmez).

Koşum: pytest backend/tests/test_learning_thresholds.py --noconftest
"""

import json

import pytest

from app.learning.labels import FeedbackRecord, TRAINING_READY, synthetic_feedback
from app.learning.thresholds import (
    ARTIFACT_PATH,
    DEFAULT_ERROR_BUDGET,
    NO_AUTO_REPLY,
    SAFETY_FLOOR,
    build_report,
    fit_auto_reply_threshold,
    render,
    write_artifact,
)


def _rec(rid, intent, conf, outcome, status=TRAINING_READY):
    return FeedbackRecord(rid, intent, conf, outcome, status)


# ── Kapı 1: acil daima insana (havuza hiç girmez) ───────────────────────────
def test_emergency_excluded_from_pool():
    recs = [
        _rec(1, "medical_emergency", 0.99, "approved"),  # kapı: asla otomatik
        _rec(2, "ask_insurance", 0.97, "approved"),      # kapı: asla otomatik
        _rec(3, "book_appointment", 0.95, "approved"),
    ]
    rec = fit_auto_reply_threshold(recs)
    assert rec.forced_human == 2
    assert rec.pool_size == 1
    report = build_report(recs)
    assert report["gates"]["emergency_never_auto"]["emergency_in_pool"] == 0
    assert report["gates"]["emergency_never_auto"]["pass"] is True


# ── Kapı 2: güvenlik tabanının altına inmez ─────────────────────────────────
def test_threshold_never_below_floor():
    # Hepsi düşük güvende ama onaylı — yine de taban altına inilmemeli.
    recs = [_rec(i, "book_appointment", 0.50 + i * 0.01, "approved") for i in range(5)]
    rec = fit_auto_reply_threshold(recs)
    assert rec.recommended_threshold >= SAFETY_FLOOR


# ── Eşik uydurma: bütçeyi karşılayan en küçük eşik ──────────────────────────
def test_fit_picks_smallest_threshold_meeting_budget():
    rec = fit_auto_reply_threshold(synthetic_feedback())
    assert rec.recommended_threshold == 0.90
    assert rec.error_rate <= DEFAULT_ERROR_BUDGET
    assert rec.met_budget is True
    assert rec.pool_size == 6
    assert rec.forced_human == 1  # 104 medical_emergency
    assert rec.coverage == pytest.approx(2 / 6, abs=1e-3)


# ── Bütçe imkânsızsa otomasyon güvenli şekilde kapanır ──────────────────────
def test_no_auto_reply_when_budget_unreachable():
    # Taban-üstü tüm kayıtlar hatalı (düzeltme) → hiçbir eşik bütçeyi tutmaz.
    recs = [
        _rec(1, "book_appointment", 0.95, "edited"),
        _rec(2, "book_appointment", 0.85, "edited"),
        _rec(3, "ask_price", 0.80, "rejected"),
    ]
    rec = fit_auto_reply_threshold(recs)
    assert rec.recommended_threshold >= NO_AUTO_REPLY
    assert rec.met_budget is False
    assert rec.coverage == 0.0
    # Otomasyonu kapatmak güvenlidir → kapılar yine geçer.
    report = build_report(recs)
    assert report["overall_pass"] is True


# ── Rapor kapıları ──────────────────────────────────────────────────────────
def test_report_gates_pass_on_synthetic():
    report = build_report(synthetic_feedback())
    assert report["overall_pass"] is True
    for gate in ("emergency_never_auto", "floor_respected", "error_budget_met"):
        assert report["gates"][gate]["pass"] is True
    assert "GEÇTİ" in render(report)


def test_empty_records_safe():
    rec = fit_auto_reply_threshold([])
    assert rec.recommended_threshold >= NO_AUTO_REPLY
    assert rec.pool_size == 0
    assert build_report([])["overall_pass"] is True


# ── Determinizm + artefakt ──────────────────────────────────────────────────
def test_report_is_deterministic():
    a = build_report(synthetic_feedback())
    b = build_report(synthetic_feedback())
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_write_and_roundtrip(tmp_path):
    report = build_report(synthetic_feedback())
    path = write_artifact(report, tmp_path / "thresholds.json")
    assert json.loads(path.read_text(encoding="utf-8")) == report


def test_committed_artifact_is_fresh():
    if not ARTIFACT_PATH.exists():
        pytest.skip("artefakt henüz üretilmemiş")
    committed = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    fresh = build_report(synthetic_feedback())
    assert committed == fresh, "thresholds.json bayat — `python -m app.learning.thresholds` ile yenile"
