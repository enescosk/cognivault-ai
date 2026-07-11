"""Prod ops — dağıtım öncesi güvenlik preflight testleri.

Saf-import; `--noconftest` ile koşar. Settings env dosyasından yalıtılır
(`_env_file=None`) → deterministik.
"""

import json
from pathlib import Path
import subprocess
import sys

from app.core.config import Settings
from app.ops.preflight import (
    ARTIFACT_PATH,
    STRONG_TEST_JWT,
    build_report,
    evaluate_production_config,
    parse_migration_graph,
)


def _prod(**overrides):
    base = {"environment": "production", "jwt_secret": STRONG_TEST_JWT}
    base.update(overrides)
    return Settings(_env_file=None, **base)


# ── Migration grafiği ────────────────────────────────────────────────────────


def test_migration_graph_has_single_head():
    graph = parse_migration_graph()
    assert len(graph["heads"]) == 1, graph["heads"]
    assert graph["heads"][0] == "0011_clinical_voice_qa_runs"


def test_migration_graph_has_single_base():
    graph = parse_migration_graph()
    assert graph["bases"] == ["0001_baseline"]


def test_migration_graph_parses_all_files():
    graph = parse_migration_graph()
    # 12 revizyon dosyası → 12 revizyon.
    assert len(graph["revisions"]) == 12


# ── Guard doğrulama (kabul + red yolları) ────────────────────────────────────


def test_weak_jwt_rejected_in_prod():
    assert _prod(jwt_secret="change-me-in-production").jwt_secret_validation_error()
    assert _prod(jwt_secret="short").jwt_secret_validation_error()


def test_low_entropy_jwt_rejected_in_prod():
    assert _prod(jwt_secret="a" * 48).jwt_secret_validation_error()


def test_strong_jwt_accepted_in_prod():
    assert _prod(jwt_secret=STRONG_TEST_JWT).jwt_secret_validation_error() is None


def test_dev_jwt_unrestricted():
    assert Settings(_env_file=None, environment="development").jwt_secret_validation_error() is None


def test_seed_demo_blocked_in_prod():
    findings = evaluate_production_config(_prod(seed_demo_data=True, auto_create_schema=False))
    assert any(f["id"] == "runtime_safety" for f in findings)


def test_auto_schema_blocked_in_prod():
    findings = evaluate_production_config(_prod(auto_create_schema=True, seed_demo_data=False))
    assert any(f["id"] == "runtime_safety" for f in findings)


def test_sqlite_blocked_in_prod():
    findings = evaluate_production_config(
        _prod(database_url="sqlite:///./data/x.db", seed_demo_data=False, auto_create_schema=False)
    )
    assert any(f["id"] == "database_backend" and f["severity"] == "block" for f in findings)


def test_cors_wildcard_warned_in_prod():
    findings = evaluate_production_config(
        _prod(
            database_url="postgresql+psycopg://u:p@db/appdb",
            cors_origins="*",
            seed_demo_data=False,
            auto_create_schema=False,
        )
    )
    assert any(f["id"] == "cors_wildcard" and f["severity"] == "warn" for f in findings)


def test_clean_prod_profile_has_no_blocking_findings():
    findings = evaluate_production_config(
        _prod(
            database_url="postgresql+psycopg://u:p@db:5432/appdb",
            seed_demo_data=False,
            auto_create_schema=False,
            cors_origins="https://klinik.example",
        )
    )
    assert [f for f in findings if f["severity"] == "block"] == []


def test_non_local_residency_is_warned():
    findings = evaluate_production_config(
        _prod(
            database_url="postgresql+psycopg://u:p@db/appdb",
            seed_demo_data=False,
            auto_create_schema=False,
            cors_origins="https://klinik.example",
            clinical_data_residency_default="global",
        )
    )
    assert any(f["id"] == "residency" for f in findings)


# ── Rapor ────────────────────────────────────────────────────────────────────


def test_report_all_gates_pass():
    report = build_report()
    for key, gate in report["gates"].items():
        assert gate["pass"], f"kapı düştü: {key} → {gate}"
    assert report["overall_pass"] is True
    assert report["safe_prod_profile_blocking_findings"] == []
    assert report["runbook_remaining"]


def test_report_is_deterministic():
    a = json.dumps(build_report(), ensure_ascii=False, sort_keys=True)
    b = json.dumps(build_report(), ensure_ascii=False, sort_keys=True)
    assert a == b


def test_committed_artifact_is_fresh():
    committed = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    assert committed == build_report()


def test_cli_smoke_exits_zero():
    proc = subprocess.run(
        [sys.executable, "-m", "app.ops.preflight", "--no-save", "--json"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["overall_pass"] is True
