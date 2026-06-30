"""İP-3.8 / İP-3.9 — yerel yığın gecikme + kalite raporu testleri.

Gecikme rakamları duvar-saati olduğundan ham süreleri DEĞİL; deterministik
mantığı (yüzdelik hesabı, bütçe kapısı), rapor yapısını ve birleşik kalite-kapısı
mantığını kilitler. Hız için küçük deneme sayısıyla koşar.
"""

from __future__ import annotations

import copy
import json

import pytest

from app.perf.latency import (
    END_TO_END_BUDGET_MS,
    MODEL_STAGE_BUDGETS,
    benchmark,
    build_latency_report,
    build_perf_report,
    measured_stages,
    passes_budget,
    percentile,
    render_latency,
    render_perf,
    summarize,
)

TRIALS = 30


@pytest.fixture(scope="module")
def latency():
    return build_latency_report(trials=TRIALS, warmup=5)


# ── Saf yüzdelik / özet ──────────────────────────────────────────────────────


def test_percentile_linear_interpolation():
    assert percentile([1, 2, 3, 4], 50) == 2.5
    assert percentile([1, 2, 3, 4, 5], 50) == 3.0
    assert percentile([10], 50) == 10.0
    assert percentile([1, 2, 3, 4, 5], 100) == 5.0
    assert percentile([1, 2, 3, 4, 5], 0) == 1.0


def test_percentile_monotonic_in_q():
    data = [5.0, 1.0, 9.0, 3.0, 7.0]
    s = sorted(data)
    vals = [percentile(s, q) for q in (0, 25, 50, 75, 95, 99, 100)]
    assert vals == sorted(vals)


def test_percentile_rejects_bad_input():
    with pytest.raises(ValueError):
        percentile([], 50)
    with pytest.raises(ValueError):
        percentile([1, 2], -1)
    with pytest.raises(ValueError):
        percentile([1, 2], 101)


def test_summarize_fields_and_ordering():
    out = summarize([3.0, 1.0, 2.0, 5.0, 4.0])
    assert out["n"] == 5
    assert out["min_ms"] == 1.0
    assert out["max_ms"] == 5.0
    assert out["mean_ms"] == 3.0
    assert out["p50_ms"] <= out["p95_ms"] <= out["p99_ms"]


# ── Benchmark / bütçe kapısı ─────────────────────────────────────────────────


def test_benchmark_returns_nonnegative_samples():
    samples = benchmark(lambda: sum(range(10)), trials=15, warmup=2)
    assert len(samples) == 15
    assert all(isinstance(x, float) and x >= 0 for x in samples)


def test_passes_budget_boundary():
    assert passes_budget(5.0, 5.0) is True
    assert passes_budget(4.999, 5.0) is True
    assert passes_budget(5.001, 5.0) is False


# ── Ölçülen aşamalar ─────────────────────────────────────────────────────────


def test_measured_stages_are_callable_and_budgeted():
    stages = measured_stages()
    assert {s.name for s in stages} == {
        "pii_masking",
        "governance_envelope",
        "intent_classification",
        "clinical_triage",
    }
    for st in stages:
        assert st.p95_budget_ms > 0
        st.call()  # çağrılabilir ve hata atmamalı


# ── Gecikme raporu yapısı ────────────────────────────────────────────────────


def test_latency_report_structure(latency):
    assert latency["ip"] == "3.8"
    assert latency["trials"] == TRIALS
    for name, s in latency["measured_stages"].items():
        assert {"label", "summary", "p95_budget_ms", "pass"} <= set(s)
        assert isinstance(s["pass"], bool)
        assert s["summary"]["p95_ms"] >= 0


def test_critical_path_p95_is_sum_of_stage_p95(latency):
    total = sum(s["summary"]["p95_ms"] for s in latency["measured_stages"].values())
    assert latency["critical_path_p95_ms"] == pytest.approx(round(total, 4))


def test_end_to_end_estimate_equals_critical_plus_model_budgets(latency):
    model_sum = sum(m["p95_budget_ms"] for m in MODEL_STAGE_BUDGETS.values())
    expected = round(latency["critical_path_p95_ms"] + model_sum, 4)
    assert latency["end_to_end"]["p95_estimate_ms"] == pytest.approx(expected)
    assert latency["end_to_end"]["budget_ms"] == END_TO_END_BUDGET_MS


def test_overall_pass_is_conjunction(latency):
    assert latency["overall_pass"] == (
        latency["measured_stages_pass"] and latency["end_to_end"]["pass"]
    )


def test_sample_text_preview_has_no_raw_pii(latency):
    preview = latency["sample_text_masked"]
    assert "12345678901" not in preview
    assert "[REDACTED]" in preview


def test_latency_report_json_serializable(latency):
    assert json.loads(json.dumps(latency, ensure_ascii=False))["ip"] == "3.8"


def test_report_shape_is_deterministic():
    a = build_latency_report(trials=5, warmup=1)
    b = build_latency_report(trials=5, warmup=1)
    # Süreler değişir; YAPI (aşama adları, bütçeler, model hedefleri) sabittir.
    assert set(a["measured_stages"]) == set(b["measured_stages"])
    assert {n: s["p95_budget_ms"] for n, s in a["measured_stages"].items()} == {
        n: s["p95_budget_ms"] for n, s in b["measured_stages"].items()
    }
    assert a["model_stage_budgets"] == b["model_stage_budgets"]


# ── Negatif / kapı testleri ──────────────────────────────────────────────────


def test_render_flags_over_budget_stage(latency):
    broken = copy.deepcopy(latency)
    stage = next(iter(broken["measured_stages"].values()))
    stage["pass"] = False
    broken["measured_stages_pass"] = False
    broken["overall_pass"] = False
    text = render_latency(broken)
    assert "❌" in text
    assert "aşıldı" in text


# ── Birleşik gecikme + kalite (İP-3.9) ───────────────────────────────────────


def test_perf_report_combines_latency_and_quality():
    report = build_perf_report(trials=5, warmup=1)
    assert report["ip"] == "3.9"
    assert "latency" in report and "quality" in report
    assert report["overall_pass"] == (
        report["latency"]["overall_pass"] and report["quality"]["overall_pass"]
    )


def test_perf_render_contains_both_sections():
    report = build_perf_report(trials=5, warmup=1)
    text = render_perf(report)
    assert "Gecikme" in text
    assert "Klinik kalite" in text
    assert "BİRLEŞİK GENEL" in text
