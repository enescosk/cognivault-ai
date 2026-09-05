"""İP-6.1 — Abonelik + başarı-bazlı faturalama testleri (saf-import, DB gerektirmez).

Koşum: pytest backend/tests/test_billing_success.py --noconftest
"""

import json

import pytest

from app.billing.success_billing import (
    ARTIFACT_PATH,
    GROWTH,
    MONTHLY_BASE_TL,
    SUCCESS_FEE_CAP_MONTHS,
    SUCCESS_FEE_PER_APPOINTMENT_TL,
    AppointmentRecord,
    ClinicMonth,
    appointment_billing,
    build_report,
    render,
    summarize_month,
    synthetic_clinic_months,
    write_artifact,
)


def _appt(ref, status="completed", kvkk=True, audit=True, human=False):
    return AppointmentRecord(ref, status, kvkk, audit, human)


# ── KVKK kapısı ─────────────────────────────────────────────────────────────
def test_kvkk_incomplete_not_billable():
    ok, blockers = appointment_billing(_appt("x", kvkk=False))
    assert not ok and "kvkk_eksik" in blockers


def test_kvkk_complete_billable():
    ok, blockers = appointment_billing(_appt("x", kvkk=True))
    assert ok and blockers == []


# ── Audit kapısı ────────────────────────────────────────────────────────────
def test_audit_missing_not_billable():
    ok, blockers = appointment_billing(_appt("x", audit=False))
    assert not ok and "audit_eksik" in blockers


def test_audit_logged_billable():
    ok, _ = appointment_billing(_appt("x", audit=True))
    assert ok


# ── İnsan-inceleme kapısı ───────────────────────────────────────────────────
def test_human_review_not_billable():
    ok, blockers = appointment_billing(_appt("x", human=True))
    assert not ok and "insan_incelemesi" in blockers


def test_no_human_review_billable():
    ok, _ = appointment_billing(_appt("x", human=False))
    assert ok


# ── No-show / iptal kapısı ──────────────────────────────────────────────────
def test_no_show_not_billable():
    ok, blockers = appointment_billing(_appt("x", status="no_show"))
    assert not ok and "durum_no_show" in blockers


def test_cancelled_not_billable():
    ok, blockers = appointment_billing(_appt("x", status="cancelled"))
    assert not ok and "durum_cancelled" in blockers


def test_incomplete_status_not_billable():
    ok, blockers = appointment_billing(_appt("x", status="confirmed"))
    assert not ok and "tamamlanmadi" in blockers


def test_completed_status_billable():
    ok, _ = appointment_billing(_appt("x", status="completed"))
    assert ok


# ── Aylık özet: sabit + başarı ücreti ───────────────────────────────────────
def test_growth_success_fee_computed():
    cm = ClinicMonth("C", GROWTH, 4, tuple(_appt(f"A{i}") for i in range(10)))
    s = summarize_month(cm)
    assert s["n_billable"] == 10
    assert s["success_fee_raw_tl"] == 10 * SUCCESS_FEE_PER_APPOINTMENT_TL[GROWTH]
    assert s["total_tl"] == MONTHLY_BASE_TL[GROWTH] + 10 * 75.0
    assert s["cap_applies"] is False


def test_starter_has_no_success_fee():
    cm = ClinicMonth("C", "starter", 1, tuple(_appt(f"A{i}") for i in range(50)))
    s = summarize_month(cm)
    assert s["success_fee_raw_tl"] == 0.0
    assert s["total_tl"] == MONTHLY_BASE_TL["starter"]


def test_blocked_appointments_excluded_from_billing():
    cm = ClinicMonth(
        "C", GROWTH, 4,
        (_appt("ok"), _appt("no", status="no_show"), _appt("k", kvkk=False), _appt("h", human=True)),
    )
    s = summarize_month(cm)
    assert s["billable_refs"] == ["ok"]
    assert set(s["blocked"]) == {"no", "k", "h"}


# ── Tavan kapısı ────────────────────────────────────────────────────────────
def test_cap_applies_first_three_months():
    # 300 tamamlanan × 75 = 22.500 > 18.500 tavan → kırpılır.
    appts = tuple(_appt(f"A{i}") for i in range(300))
    for month in range(1, SUCCESS_FEE_CAP_MONTHS + 1):
        s = summarize_month(ClinicMonth("C", GROWTH, month, appts))
        assert s["cap_applies"] is True
        assert s["success_fee_capped_tl"] == MONTHLY_BASE_TL[GROWTH]
        assert s["success_fee_removed_by_cap_tl"] == 22500.0 - 18500.0
        assert s["total_tl"] == 2 * MONTHLY_BASE_TL[GROWTH]


def test_cap_not_applied_after_window():
    appts = tuple(_appt(f"A{i}") for i in range(300))
    s = summarize_month(ClinicMonth("C", GROWTH, SUCCESS_FEE_CAP_MONTHS + 1, appts))
    assert s["cap_applies"] is False
    assert s["success_fee_capped_tl"] == 22500.0
    assert s["success_fee_removed_by_cap_tl"] == 0.0


def test_cap_not_binding_below_threshold():
    # Az randevu → tavana çarpmaz, kırpma olmaz.
    appts = tuple(_appt(f"A{i}") for i in range(10))
    s = summarize_month(ClinicMonth("C", GROWTH, 1, appts))
    assert s["cap_applies"] is True
    assert s["success_fee_removed_by_cap_tl"] == 0.0
    assert s["success_fee_capped_tl"] == 750.0


# ── Rapor kapıları ──────────────────────────────────────────────────────────
def test_report_gates_pass():
    report = build_report()
    assert report["overall_pass"] is True
    for g in report["gates"].values():
        assert g["pass"] is True
    assert "GEÇTİ" in render(report)


def test_report_cap_actually_engaged():
    # Sentetik senaryo tavanı gerçekten tetiklemeli (aksi halde kapı boş test olur).
    report = build_report()
    c001 = next(s for s in report["summaries"] if s["clinic_ref"] == "C-001")
    assert c001["success_fee_removed_by_cap_tl"] == 4000.0


def test_gate_fails_when_no_show_billed():
    # Kapı gerçekten koruyor mu: no-show tamamlanmış gibi işaretlenirse motor onu
    # ücretlendirmez; ama kapının negatifini görmek için manuel bir ihlal kurgula.
    bad = ClinicMonth("C", GROWTH, 4, (_appt("n", status="no_show"),))
    s = summarize_month(bad)
    assert "n" not in s["billable_refs"]


# ── Determinizm + artefakt ──────────────────────────────────────────────────
def test_report_is_deterministic():
    a = build_report()
    b = build_report()
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_write_and_roundtrip(tmp_path):
    report = build_report()
    path = write_artifact(report, tmp_path / "success_billing.json")
    assert json.loads(path.read_text(encoding="utf-8")) == report


def test_committed_artifact_is_fresh():
    if not ARTIFACT_PATH.exists():
        pytest.skip("artefakt henüz üretilmemiş")
    committed = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    fresh = build_report()
    assert committed == fresh, "success_billing.json bayat — `python -m app.billing.success_billing` ile yenile"


def test_synthetic_scenarios_cover_all_gates():
    # Sentetik veri her kapı için en az bir engelli randevu içermeli.
    reasons = set()
    for cm in synthetic_clinic_months():
        for appt in cm.appointments:
            _, blockers = appointment_billing(appt)
            reasons.update(blockers)
    assert {"kvkk_eksik", "audit_eksik", "insan_incelemesi", "durum_no_show", "durum_cancelled"} <= reasons
