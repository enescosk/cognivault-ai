"""İP-6.2 — tek komut klinik onboarding provizyonu testleri.

Saf-import; `--noconftest` ile koşar. DB olarak bellek-içi SQLite kullanır
(gerçek şema `Base.metadata`'dan kurulur) — HTTP/fixture bağımlılığı yok.
"""

from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys

import pytest
from sqlalchemy import select

from app.models.entities import Clinic, Doctor, KVKKDisclosureVersion
from app.onboarding import provision as mod
from app.onboarding.provision import (
    ARTIFACT_PATH,
    DEMO_INTAKE,
    build_report,
    provision,
    validate_intake,
)


def _fresh_db():
    return mod._memory_session()


# ── Doğrulama ────────────────────────────────────────────────────────────────


def test_demo_intake_is_valid():
    assert validate_intake(DEMO_INTAKE) == []


def test_invalid_slug_is_rejected():
    bad = replace(DEMO_INTAKE, slug="Büyük Harf ve boşluk")
    assert any("Slug" in issue for issue in validate_intake(bad))


def test_unknown_specialty_code_is_rejected():
    bad = replace(
        DEMO_INTAKE,
        doctors=(mod.IntakeDoctor(full_name="Dr. X", specialty_code="kardiyoloji"),),
    )
    assert any("ontolojide yok" in issue for issue in validate_intake(bad))


def test_shadow_threshold_below_safety_floor_is_rejected():
    bad = replace(DEMO_INTAKE, shadow_review_threshold=0.5, ai_auto_reply_threshold=0.9)
    assert any("güvenlik tabanı" in issue for issue in validate_intake(bad))


def test_missing_owner_is_rejected():
    bad = replace(
        DEMO_INTAKE,
        staff=(
            mod.IntakeStaff(
                full_name="Sadece Operatör",
                email="op@x.example",
                role="operator",
                initial_password="uzun-parola-1",
            ),
        ),
    )
    assert any("'owner'" in issue for issue in validate_intake(bad))


def test_provision_refuses_invalid_intake():
    db = _fresh_db()
    with pytest.raises(ValueError, match="Intake geçersiz"):
        provision(db, replace(DEMO_INTAKE, slug="X"))


# ── Provizyon davranışı ──────────────────────────────────────────────────────


def test_single_run_creates_expected_counts():
    db = _fresh_db()
    result = provision(db, DEMO_INTAKE)
    assert result.created == {
        "clinic": 1,
        "branch": len(DEMO_INTAKE.branches),
        "doctor": len(DEMO_INTAKE.doctors),
        "service": len(DEMO_INTAKE.services),
        "user": len(DEMO_INTAKE.staff),
        "membership": len(DEMO_INTAKE.staff),
        "kvkk_disclosure": 1,
    }
    assert result.updated == {}


def test_second_run_is_full_noop():
    db = _fresh_db()
    provision(db, DEMO_INTAKE)
    second = provision(db, DEMO_INTAKE)
    assert second.total_created == 0
    assert second.total_updated == 0
    assert len(db.scalars(select(Clinic)).all()) == 1
    assert len(db.scalars(select(Doctor)).all()) == len(DEMO_INTAKE.doctors)


def test_changed_field_updates_without_duplication():
    db = _fresh_db()
    provision(db, DEMO_INTAKE)
    renamed = replace(DEMO_INTAKE, name="Demo Diş Kliniği (Yeni Ad)")
    result = provision(db, renamed)
    assert result.created == {}
    assert result.updated.get("clinic") == 1
    clinics = db.scalars(select(Clinic)).all()
    assert len(clinics) == 1
    assert clinics[0].name == "Demo Diş Kliniği (Yeni Ad)"


def test_new_kvkk_version_rotates_active_disclosure():
    db = _fresh_db()
    provision(db, DEMO_INTAKE)
    v2 = replace(DEMO_INTAKE, kvkk_version="v2.0", kvkk_text="Avukat onaylı nihai metin.")
    provision(db, v2)
    disclosures = db.scalars(select(KVKKDisclosureVersion)).all()
    active = [d for d in disclosures if d.is_active]
    assert len(disclosures) == 2
    assert len(active) == 1
    assert active[0].version == "v2.0"


def test_tenant_isolation_between_two_clinics():
    db = _fresh_db()
    first = provision(db, DEMO_INTAKE)
    other = provision(db, mod._second_clinic_intake())
    assert first.clinic_id != other.clinic_id
    first_doctors = db.scalars(select(Doctor).where(Doctor.clinic_id == first.clinic_id)).all()
    other_doctors = db.scalars(select(Doctor).where(Doctor.clinic_id == other.clinic_id)).all()
    assert len(first_doctors) == len(DEMO_INTAKE.doctors)
    assert len(other_doctors) == 1
    assert {d.id for d in first_doctors}.isdisjoint({d.id for d in other_doctors})


# ── Rapor ────────────────────────────────────────────────────────────────────


def test_report_all_gates_pass():
    report = build_report()
    for key, gate in report["gates"].items():
        assert gate["pass"], f"kapı düştü: {key} → {gate}"
    assert report["overall_pass"] is True
    assert report["remaining"]  # kalan saha işleri dürüstçe listelenir


def test_report_acceptance_checks_cover_playbook_scenarios():
    checks = build_report()["gates"]["acceptance_scenarios"]["checks"]
    assert set(checks) == {
        "kvkk_versioned",
        "emergency_escalation",
        "identity_masking",
        "ambiguous_abstains",
        "booking_prereqs",
        "staff_access",
        "safety_thresholds",
    }


def test_report_is_deterministic():
    a = json.dumps(build_report(), ensure_ascii=False, sort_keys=True)
    b = json.dumps(build_report(), ensure_ascii=False, sort_keys=True)
    assert a == b


def test_committed_artifact_is_fresh():
    committed = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    assert committed == build_report()


def test_cli_smoke_exits_zero():
    proc = subprocess.run(
        [sys.executable, "-m", "app.onboarding.provision", "--no-save", "--json"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["overall_pass"] is True
