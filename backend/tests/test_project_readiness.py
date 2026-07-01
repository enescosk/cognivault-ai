"""Fazli proje hazirlik panosu testleri (saf-import, DB gerektirmez).

Kosum: pytest backend/tests/test_project_readiness.py --noconftest
"""

import json

from app.project_readiness import build_project_readiness, main, render


def test_technical_board_is_green_but_project_not_production_ready():
    report = build_project_readiness()

    assert report["technical_overall_pass"] is True
    assert report["production_ready"] is False
    assert report["recommended_label"] == "production-oriented pilot"


def test_counts_match_gate_statuses():
    report = build_project_readiness()
    gates = report["gates"]

    assert report["counts"]["total"] == len(gates)
    for status in ("passed", "partial", "pending", "blocked"):
        assert report["counts"][status] == sum(1 for gate in gates if gate["status"] == status)


def test_distillation_summary_exposes_dataset_artifact():
    report = build_project_readiness()

    assert report["distillation_summary"]["overall_pass"] is True
    assert report["distillation_summary"]["dataset_artifact"] == "distillation_dataset.jsonl"
    assert report["distillation_summary"]["eval_input_artifact"] == "distillation_eval_inputs.jsonl"
    assert report["distillation_summary"]["total_examples"] >= 500
    assert 0 <= report["distillation_summary"]["baseline"]["validation_exact_label_accuracy"] <= 1


def test_next_actions_are_open_and_priority_ordered():
    report = build_project_readiness()
    open_ids = [gate["id"] for gate in report["gates"] if gate["status"] != "passed"]

    assert report["next_actions"]
    assert all(action["id"] in open_ids for action in report["next_actions"])
    assert report["next_actions"][0]["id"] == "ip3_6_model_distillation"
    assert any(action["id"] == "kvkk_legal_approval" for action in report["next_actions"])


def test_render_contains_truthful_label_and_remaining_work():
    text = render(build_project_readiness())

    assert "production-oriented pilot" in text
    assert "NOT PRODUCTION-READY" in text
    assert "Siradaki aksiyonlar" in text


def test_deterministic():
    first = build_project_readiness()
    second = build_project_readiness()

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_cli_default_reports_success_but_strict_fails_until_production_ready():
    assert main(["--no-save"]) == 0
    assert main(["--no-save", "--strict"]) == 1
