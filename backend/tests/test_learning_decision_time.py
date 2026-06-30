"""İP-4.4 — Onay karar süresi ölçüm testleri (saf-import, DB gerektirmez).

Koşum: pytest backend/tests/test_learning_decision_time.py --noconftest
"""

import json

import pytest

from app.learning.decision_time import (
    ARTIFACT_PATH,
    TARGET_SECONDS,
    ReviewTiming,
    bottleneck,
    build_report,
    optimization_hint,
    percentile,
    render,
    summarize,
    synthetic_timings,
    write_artifact,
)


# ── Yüzdelik doğruluğu ──────────────────────────────────────────────────────
def test_percentile_interpolation():
    assert percentile([1, 2, 3, 4], 0.5) == 2.5
    assert percentile([1, 2, 3, 4], 0.0) == 1
    assert percentile([1, 2, 3, 4], 1.0) == 4
    assert percentile([], 0.5) == 0.0
    assert percentile([7], 0.9) == 7


# ── Özet + darboğaz ─────────────────────────────────────────────────────────
def test_summarize_keys():
    s = summarize(synthetic_timings())
    for k in ("count", "p50", "p90", "p95", "mean", "max", "by_reason_mean"):
        assert k in s
    assert s["count"] == 220


def test_bottleneck_is_slowest_reason():
    timings = [
        ReviewTiming(1, 5.0, "fast", "approved"),
        ReviewTiming(2, 25.0, "slow", "edited"),
        ReviewTiming(3, 6.0, "fast", "approved"),
    ]
    reason, mean = bottleneck(timings)
    assert reason == "slow"
    assert mean == 25.0


def test_optimization_hint_nonempty():
    assert isinstance(optimization_hint("ask_insurance"), str)
    assert optimization_hint(None)  # fallback da boş değil


# ── Kabul ölçütü: p95 < 30 sn ───────────────────────────────────────────────
def test_meets_target_on_synthetic():
    report = build_report()
    assert report["stats"]["p95"] <= TARGET_SECONDS
    assert report["overall_pass"] is True
    assert "GEÇTİ" in render(report)


def test_gate_fails_when_slow():
    slow = [ReviewTiming(i, 40.0, "requires_human_review", "edited") for i in range(10)]
    report = build_report(slow)
    assert report["overall_pass"] is False
    assert report["gates"]["p95_under_target"]["pass"] is False


# ── Determinizm + artefakt ──────────────────────────────────────────────────
def test_report_is_deterministic():
    a = build_report()
    b = build_report()
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_write_and_roundtrip(tmp_path):
    report = build_report()
    path = write_artifact(report, tmp_path / "decision_time.json")
    assert json.loads(path.read_text(encoding="utf-8")) == report


def test_committed_artifact_is_fresh():
    if not ARTIFACT_PATH.exists():
        pytest.skip("artefakt henüz üretilmemiş")
    committed = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    fresh = build_report()
    assert committed == fresh, "decision_time.json bayat — `python -m app.learning.decision_time` ile yenile"
