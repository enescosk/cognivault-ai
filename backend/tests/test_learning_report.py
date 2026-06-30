"""İP-4 — Konsolide hekim-döngülü öğrenme panosu testleri.

Panonun altı motoru doğru orkestre ettiğini, her motorun kapı durumunu sadık
yansıttığını, öne çıkan metriklerin motor raporlarıyla tutarlı olduğunu, panonun
deterministik + JSON-serileştirilebilir olduğunu ve commit'li artefaktın üreticiyle
güncel kaldığını doğrular.
"""

from __future__ import annotations

import copy
import json

import pytest

from app.learning import decision_time, labels, noshow, recall, slots, thresholds
from app.learning.report import (
    DASHBOARD_ARTIFACT,
    ENGINES,
    build_learning_dashboard,
    render,
    save_dashboard,
)


@pytest.fixture(scope="module")
def dashboard():
    return build_learning_dashboard()


def test_dashboard_covers_all_six_engines(dashboard):
    assert dashboard["engine_count"] == 6
    assert set(dashboard["summary"]) == {"4.2", "4.3", "4.4", "4.5", "4.6", "4.7"}
    assert set(dashboard["engines"]) == set(dashboard["summary"])


def test_summary_pass_matches_engine_overall_pass(dashboard):
    for ip, s in dashboard["summary"].items():
        assert s["pass"] == dashboard["engines"][ip]["overall_pass"]


def test_overall_pass_is_conjunction(dashboard):
    assert dashboard["overall_pass"] == all(
        s["pass"] for s in dashboard["summary"].values()
    )


def test_all_engines_pass_on_synthetic_defaults(dashboard):
    for ip, s in dashboard["summary"].items():
        assert s["pass"] is True, f"İP-{ip} kapısı kaldı"
    assert dashboard["overall_pass"] is True


def test_headline_metrics_consistent_with_engine_reports(dashboard):
    m = dashboard["headline_metrics"]
    e = dashboard["engines"]
    assert m["no_show_auc_test"] == e["4.5"]["metrics"]["auc_test"]
    assert m["decision_p95_seconds"] == e["4.4"]["stats"]["p95"]
    assert m["auto_reply_threshold"] == e["4.3"]["recommendation"]["recommended_threshold"]
    assert m["rlhf_labels_count"] == e["4.2"]["labels"]["count"]
    assert m["slot_recommendations"] == len(e["4.6"]["recommendations"])
    assert m["recall_scheduled"] == len(e["4.7"]["scheduled"])


def test_no_show_auc_meets_target(dashboard):
    # İP-4.5 başarı ölçütü AUC ≥ 0.75; pano bunu sadık taşımalı.
    assert dashboard["headline_metrics"]["no_show_auc_test"] >= 0.75


def test_engines_table_matches_module_build_reports():
    # ENGINES kayıt tablosu her motorun gerçek build_report'una bağlı olmalı.
    assert ENGINES[0][1] == "rlhf_labels"
    assert labels.build_report(labels.synthetic_feedback())["ip"] == "4.2"
    assert thresholds.build_report(labels.synthetic_feedback())["ip"] == "4.3"
    assert decision_time.build_report()["ip"] == "4.4"
    assert noshow.build_report()["ip"] == "4.5"
    assert slots.build_report()["ip"] == "4.6"
    assert recall.build_report()["ip"] == "4.7"


def test_dashboard_is_deterministic():
    assert build_learning_dashboard() == build_learning_dashboard()


def test_dashboard_json_serializable_and_roundtrips(dashboard):
    assert json.loads(json.dumps(dashboard, ensure_ascii=False)) == dashboard


def test_render_flags_failure_on_injected_engine_fail(dashboard):
    broken = copy.deepcopy(dashboard)
    broken["summary"]["4.5"]["pass"] = False
    broken["overall_pass"] = False
    text = render(broken)
    assert "❌" in text
    assert "kaldı" in text


def test_render_lists_all_engines(dashboard):
    text = render(dashboard)
    for ip in ("4.2", "4.3", "4.4", "4.5", "4.6", "4.7"):
        assert f"İP-{ip}" in text


def test_committed_artifact_matches_builder(dashboard):
    if not DASHBOARD_ARTIFACT.exists():
        pytest.skip("learning_report.json artefaktı yok")
    committed = json.loads(DASHBOARD_ARTIFACT.read_text(encoding="utf-8"))
    assert committed == dashboard
