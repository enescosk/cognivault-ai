"""Outbox kanıt panosu testleri."""

from __future__ import annotations

from app.ops.outbox import build_report, main, render


def test_outbox_report_passes_all_gates():
    report = build_report()

    assert report["overall_pass"] is True
    assert report["summary"]["gates_passed"] == report["summary"]["gates_total"]
    assert report["summary"]["gates_total"] == 7


def test_outbox_report_contains_dead_letter_gate():
    report = build_report()

    gate_ids = {gate["id"] for gate in report["gates"]}
    assert "unknown_handler_dead_letter" in gate_ids
    assert "max_attempts_dead_letter" in gate_ids
    assert "operator_summary_contract" in gate_ids
    assert "postgres_skip_locked" in gate_ids


def test_render_contains_verdict():
    assert "Genel: PASS" in render(build_report())


def test_cli_exit_zero():
    assert main(["--no-save"]) == 0
