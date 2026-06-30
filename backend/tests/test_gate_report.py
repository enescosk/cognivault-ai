"""İP-2.8 — kapı ihlal-edilemezliği kanıt raporu testleri."""

from __future__ import annotations

import copy
import json

import pytest

from app.governance.adversarial import IDENTIFIER_PATTERNS  # noqa: F401  (varlık kontrolü)
from app.governance.gate_report import (
    GATE_ARTIFACT,
    MIN_SCENARIOS,
    build_gate_dashboard,
    render,
    save_dashboard,
)
from app.services.clinical_compliance_service import IDENTIFIER_PATTERNS as PATTERNS


@pytest.fixture(scope="module")
def dashboard():
    return build_gate_dashboard()


def test_meets_scenario_and_violation_targets(dashboard):
    assert dashboard["scenario_count"] >= MIN_SCENARIOS
    assert dashboard["violation_count"] == 0
    assert dashboard["overall_pass"] is True


def test_all_leak_gates_pass(dashboard):
    for gate, v in dashboard["leak_gates"].items():
        assert v["pass"] is True, f"{gate} ihlali: {v['violations']}"


def test_audit_trail_samples_have_no_pii_leak(dashboard):
    for sample in dashboard["audit_trail_samples"]:
        preview = sample["redacted_preview"]
        for pattern in PATTERNS:
            assert not pattern.search(preview), f"PII sızıntısı: {preview!r}"


def test_emergency_sample_does_not_auto_send(dashboard):
    emg = [s for s in dashboard["audit_trail_samples"] if s["intent"] == "medical_emergency"]
    assert emg and all(s["auto_send_allowed"] is False for s in emg)


def test_dashboard_json_serializable_and_roundtrips(dashboard):
    assert json.loads(json.dumps(dashboard, ensure_ascii=False)) == dashboard


def test_dashboard_is_deterministic():
    assert build_gate_dashboard() == build_gate_dashboard()


def test_render_flags_failure_on_injected_violation(dashboard):
    broken = copy.deepcopy(dashboard)
    broken["violation_count"] = 1
    broken["violations"] = {"saldırgan metin": ["pii_leak"]}
    broken["overall_pass"] = False
    text = render(broken)
    assert "❌" in text
    assert "İHLALLER" in text


def test_committed_artifact_matches_builder(dashboard):
    if not GATE_ARTIFACT.exists():
        pytest.skip("gate_report.json artefaktı yok")
    committed = json.loads(GATE_ARTIFACT.read_text(encoding="utf-8"))
    assert committed == dashboard
