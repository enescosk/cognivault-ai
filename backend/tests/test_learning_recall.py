"""İP-4.7 — Proaktif geri-çağırma zamanlama testleri (saf-import, DB gerektirmez).

Koşum: pytest backend/tests/test_learning_recall.py --noconftest
"""

import json

import pytest

from app.learning.recall import (
    ARTIFACT_PATH,
    CONTACT_WINDOW,
    COOLDOWN_DAYS,
    RecallCandidate,
    build_report,
    recall_priority,
    render,
    schedule_recalls,
    synthetic_candidates,
    write_artifact,
)


def _cand(ref, consent=True, since=30, overdue=20, risk=0.5, incomplete=True, urgency="medium"):
    return RecallCandidate(ref, incomplete, overdue, risk, consent, since, urgency, "sms")


# ── Rıza kapısı ─────────────────────────────────────────────────────────────
def test_no_consent_never_scheduled():
    cands = [_cand("yes", consent=True), _cand("no", consent=False, risk=0.9, urgency="high")]
    refs = {s.patient_ref for s in schedule_recalls(cands)}
    assert refs == {"yes"}


# ── Cooldown kapısı ─────────────────────────────────────────────────────────
def test_cooldown_blocks_recent_contact():
    cands = [_cand("ok", since=COOLDOWN_DAYS), _cand("recent", since=COOLDOWN_DAYS - 1)]
    refs = {s.patient_ref for s in schedule_recalls(cands)}
    assert refs == {"ok"}


# ── Sessiz saat ─────────────────────────────────────────────────────────────
def test_all_scheduled_in_contact_window():
    cands = [_cand(f"P{i}") for i in range(20)]
    sched = schedule_recalls(cands)
    assert all(CONTACT_WINDOW[0] <= s.scheduled_hour <= CONTACT_WINDOW[1] for s in sched)


# ── Öncelik mantığı ─────────────────────────────────────────────────────────
def test_priority_orders_by_urgency_and_overdue():
    hot = _cand("hot", overdue=60, risk=0.8, incomplete=True, urgency="high")
    cold = _cand("cold", overdue=2, risk=0.1, incomplete=False, urgency="low")
    p_hot, _ = recall_priority(hot)
    p_cold, _ = recall_priority(cold)
    assert p_hot > p_cold
    sched = schedule_recalls([cold, hot])
    assert sched[0].patient_ref == "hot"


def test_priority_sorted_descending():
    sched = schedule_recalls(synthetic_candidates())
    assert all(sched[i].priority >= sched[i + 1].priority for i in range(len(sched) - 1))


def test_empty_candidates():
    assert schedule_recalls([]) == []


# ── Rapor kapıları ──────────────────────────────────────────────────────────
def test_report_gates_pass():
    report = build_report()
    assert report["overall_pass"] is True
    for g in report["gates"].values():
        assert g["pass"] is True
    assert "GEÇTİ" in render(report)


def test_report_excludes_blocked_candidates():
    report = build_report()
    refs = {s["patient_ref"] for s in report["scheduled"]}
    assert "P-004" not in refs  # rıza yok
    assert "P-005" not in refs  # cooldown içinde


# ── Determinizm + artefakt ──────────────────────────────────────────────────
def test_report_is_deterministic():
    a = build_report()
    b = build_report()
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_write_and_roundtrip(tmp_path):
    report = build_report()
    path = write_artifact(report, tmp_path / "recall.json")
    assert json.loads(path.read_text(encoding="utf-8")) == report


def test_committed_artifact_is_fresh():
    if not ARTIFACT_PATH.exists():
        pytest.skip("artefakt henüz üretilmemiş")
    committed = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    fresh = build_report()
    assert committed == fresh, "recall.json bayat — `python -m app.learning.recall` ile yenile"
