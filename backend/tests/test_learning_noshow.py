"""İP-4.5 — No-show risk modeli testleri (saf-import, DB gerektirmez).

Koşum: pytest backend/tests/test_learning_noshow.py --noconftest
"""

import json

import pytest

from app.learning.noshow import (
    ARTIFACT_PATH,
    AUC_TARGET,
    FEATURES,
    auc_score,
    build_report,
    render,
    synthetic_dataset,
    train_and_evaluate,
    train_logreg,
    write_artifact,
)


# ── AUC yardımcı doğruluğu ──────────────────────────────────────────────────
def test_auc_perfect_separation():
    assert auc_score([1, 1, 0, 0], [0.9, 0.8, 0.2, 0.1]) == 1.0


def test_auc_reversed():
    assert auc_score([0, 0, 1, 1], [0.9, 0.8, 0.2, 0.1]) == 0.0


def test_auc_ties_half():
    assert auc_score([1, 0], [0.5, 0.5]) == 0.5


def test_auc_degenerate_single_class():
    assert auc_score([1, 1, 1], [0.1, 0.2, 0.3]) == 0.5


# ── Kabul ölçütü: AUC ≥ 0,75 ────────────────────────────────────────────────
def test_model_meets_auc_target():
    report = build_report()
    assert report["metrics"]["auc_test"] >= AUC_TARGET
    assert report["overall_pass"] is True
    assert "GEÇTİ" in render(report)


def test_no_show_rate_realistic():
    report = build_report()
    # sentetik taban riski ~%29 — makul aralık
    assert 0.15 <= report["metrics"]["no_show_rate"] <= 0.45


# ── Öğrenilen katsayı yönleri (sinyal doğru yönde) ──────────────────────────
def test_coefficient_signs_make_sense():
    res = train_and_evaluate(synthetic_dataset())
    coeff = dict(zip(res["model"].feature_order, res["model"].weights))
    assert coeff["prior_no_shows"] > 0      # geçmiş gelmeme → risk ↑
    assert coeff["prior_completed"] < 0     # sadakat → risk ↓
    assert coeff["reminder_sent"] < 0       # hatırlatma → risk ↓


# ── risk_score: aralık + monotonluk ─────────────────────────────────────────
def test_risk_score_bounds_and_monotonic():
    model = train_and_evaluate(synthetic_dataset())["model"]
    high = {
        "lead_time_days": 28, "prior_no_shows": 5, "prior_completed": 0,
        "reminder_sent": 0, "is_first_visit": 1, "days_since_last": 320,
        "age": 35, "slot_hour": 9,
    }
    low = {
        "lead_time_days": 1, "prior_no_shows": 0, "prior_completed": 11,
        "reminder_sent": 1, "is_first_visit": 0, "days_since_last": 10,
        "age": 35, "slot_hour": 9,
    }
    rh, rl = model.risk_score(high), model.risk_score(low)
    assert 0.0 <= rl <= 1.0 and 0.0 <= rh <= 1.0
    assert rh > rl


def test_feature_order_stable():
    model = train_logreg(synthetic_dataset()[:200])
    assert model.feature_order == FEATURES
    assert len(model.weights) == len(FEATURES)


# ── Determinizm + artefakt ──────────────────────────────────────────────────
def test_report_is_deterministic():
    a = build_report()
    b = build_report()
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_write_and_roundtrip(tmp_path):
    report = build_report()
    path = write_artifact(report, tmp_path / "noshow.json")
    assert json.loads(path.read_text(encoding="utf-8")) == report


def test_committed_artifact_is_fresh():
    if not ARTIFACT_PATH.exists():
        pytest.skip("artefakt henüz üretilmemiş")
    committed = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    fresh = build_report()
    assert committed == fresh, "noshow.json bayat — `python -m app.learning.noshow` ile yenile"
