"""İP-4.6 — Dinamik slot önerisi testleri (saf-import, DB gerektirmez).

Koşum: pytest backend/tests/test_learning_slots.py --noconftest
"""

import json

import pytest

from app.learning.noshow import synthetic_dataset, train_logreg
from app.learning.slots import (
    ARTIFACT_PATH,
    RISK_THRESHOLD,
    Slot,
    build_report,
    recommend_for_patient,
    recommend_slots,
    render,
    slot_score,
    synthetic_scenario,
    write_artifact,
)


def _slot(sid, hour=9, cap=2, peak=False, reminder=False, day=0):
    return Slot(sid, day, hour, cap, peak, reminder)


# ── Dolu slot asla önerilmez ────────────────────────────────────────────────
def test_full_slot_excluded():
    slots = [_slot("A", cap=0), _slot("B", cap=2)]
    recs = recommend_slots(slots, no_show_risk=0.3)
    assert [r.slot_id for r in recs] == ["B"]


def test_all_full_returns_empty():
    slots = [_slot("A", cap=0), _slot("B", cap=0)]
    assert recommend_slots(slots, 0.5) == []


# ── Riskli hasta: hatırlatma slotu öncelikli ────────────────────────────────
def test_high_risk_prefers_reminder_window():
    slots = [
        _slot("noremind", hour=9, reminder=False),
        _slot("remind", hour=9, reminder=True),
    ]
    recs = recommend_slots(slots, no_show_risk=0.8)
    assert recs[0].slot_id == "remind"
    assert "hatirlatma_penceresi" in recs[0].reasons


# ── Riskli hasta: yoğun (prime) slot #1 olmaz (yoğun-olmayan varken) ─────────
def test_high_risk_avoids_peak_when_alternative_exists():
    slots = [
        _slot("peak", hour=10, peak=True),
        _slot("offpeak", hour=9, peak=False),
    ]
    recs = recommend_slots(slots, no_show_risk=0.8)
    assert recs[0].slot_id == "offpeak"


# ── Güvenilir hasta: prime slot ödüllendirilir ──────────────────────────────
def test_low_risk_rewards_peak():
    s_peak, _ = slot_score(_slot("p", peak=True), no_show_risk=0.2)
    s_flat, _ = slot_score(_slot("f", peak=False), no_show_risk=0.2)
    assert s_peak > s_flat


# ── Sıralama azalan + sınırlı ───────────────────────────────────────────────
def test_sorted_descending_and_bounded():
    slots = [_slot(f"S{i}", hour=8 + i, reminder=(i % 2 == 0)) for i in range(6)]
    recs = recommend_slots(slots, 0.6, top_k=3)
    assert len(recs) == 3
    assert all(recs[i].score >= recs[i + 1].score for i in range(len(recs) - 1))


# ── İP-4.5 modeliyle entegrasyon ────────────────────────────────────────────
def test_recommend_for_patient_uses_model():
    model = train_logreg(synthetic_dataset()[:300])
    risky = {
        "lead_time_days": 28, "prior_no_shows": 5, "prior_completed": 0,
        "reminder_sent": 0, "is_first_visit": 1, "days_since_last": 300,
        "age": 30, "slot_hour": 10,
    }
    slots = [_slot("peak", hour=10, peak=True), _slot("remind", hour=9, reminder=True)]
    recs = recommend_for_patient(model, risky, slots)
    # yüksek riskli hasta → hatırlatma/yoğun-olmayan slot öne çıkar
    assert recs[0].slot_id == "remind"


# ── Rapor kapıları ──────────────────────────────────────────────────────────
def test_report_gates_pass():
    report = build_report()
    assert report["overall_pass"] is True
    for g in report["gates"].values():
        assert g["pass"] is True
    assert "GEÇTİ" in render(report)


def test_threshold_constant_sane():
    assert 0.0 < RISK_THRESHOLD < 1.0
    # senaryo riskli hasta kullanır
    risk, _, _ = synthetic_scenario()
    assert risk >= RISK_THRESHOLD


# ── Determinizm + artefakt ──────────────────────────────────────────────────
def test_report_is_deterministic():
    a = build_report()
    b = build_report()
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_write_and_roundtrip(tmp_path):
    report = build_report()
    path = write_artifact(report, tmp_path / "slots.json")
    assert json.loads(path.read_text(encoding="utf-8")) == report


def test_committed_artifact_is_fresh():
    if not ARTIFACT_PATH.exists():
        pytest.skip("artefakt henüz üretilmemiş")
    committed = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    fresh = build_report()
    assert committed == fresh, "slots.json bayat — `python -m app.learning.slots` ile yenile"
