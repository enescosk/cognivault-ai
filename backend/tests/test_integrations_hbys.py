"""İP-5.2 — HBYS/takvim adapteri dayanıklılık sözleşmesi testleri.

Saf-import; `--noconftest` ile koşar. Dış bağımlılık yok.
"""

from datetime import datetime, timedelta
import json
from pathlib import Path
import subprocess
import sys

import pytest

from app.integrations.hbys import (
    ARTIFACT_PATH,
    BookingRequest,
    InMemoryHbysAdapter,
    PermanentHbysError,
    ProcedureStep,
    SlotConflictError,
    TransientHbysError,
    book_with_procedures,
    build_report,
    sync_booking_with_retry,
)


def _req(key="k", doctor="D-1", hour=10, minutes=30):
    return BookingRequest(
        idempotency_key=key,
        external_patient_ref="P-1",
        external_doctor_ref=doctor,
        starts_at=datetime(2026, 8, 1, hour, 0),
        duration_minutes=minutes,
    )


# ── Idempotency ──────────────────────────────────────────────────────────────


def test_same_key_returns_same_ref_and_one_booking():
    adapter = InMemoryHbysAdapter()
    first = adapter.create_booking(_req())
    second = adapter.create_booking(_req())
    assert first.external_ref == second.external_ref
    assert second.deduplicated is True
    assert len(adapter.active_bookings()) == 1


def test_different_keys_create_distinct_bookings():
    adapter = InMemoryHbysAdapter()
    a = adapter.create_booking(_req(key="a", hour=9))
    b = adapter.create_booking(_req(key="b", hour=11))
    assert a.external_ref != b.external_ref
    assert len(adapter.active_bookings()) == 2


# ── Conflict ─────────────────────────────────────────────────────────────────


def test_overlapping_same_doctor_conflicts():
    adapter = InMemoryHbysAdapter()
    adapter.create_booking(_req(key="a", doctor="D-1", hour=10))
    with pytest.raises(SlotConflictError):
        overlap = BookingRequest("b", "P-2", "D-1", datetime(2026, 8, 1, 10, 15), 30)
        adapter.create_booking(overlap)


def test_same_time_different_doctor_ok():
    adapter = InMemoryHbysAdapter()
    adapter.create_booking(_req(key="a", doctor="D-1", hour=10))
    adapter.create_booking(_req(key="b", doctor="D-2", hour=10))
    assert len(adapter.active_bookings()) == 2


def test_adjacent_non_overlapping_ok():
    adapter = InMemoryHbysAdapter()
    adapter.create_booking(_req(key="a", doctor="D-1", hour=10, minutes=30))
    # 10:30 başlangıç, öncekiyle bitişik ama çakışmıyor.
    later = BookingRequest("b", "P-2", "D-1", datetime(2026, 8, 1, 10, 30), 30)
    adapter.create_booking(later)
    assert len(adapter.active_bookings()) == 2


def test_cancelled_slot_frees_the_time():
    adapter = InMemoryHbysAdapter()
    first = adapter.create_booking(_req(key="a", doctor="D-1", hour=10))
    adapter.cancel_booking(first.external_ref)
    # Aynı zaman artık serbest.
    adapter.create_booking(_req(key="b", doctor="D-1", hour=10))
    assert len(adapter.active_bookings()) == 1


# ── Retry ────────────────────────────────────────────────────────────────────


def test_transient_error_recovers_within_max_attempts():
    adapter = InMemoryHbysAdapter(
        fail_script={"k": [TransientHbysError("t1"), TransientHbysError("t2")]}
    )
    result = sync_booking_with_retry(adapter, _req(key="k"), max_attempts=3)
    assert result.status == "confirmed"
    assert adapter.create_calls == 3


def test_transient_error_exhausts_and_raises():
    adapter = InMemoryHbysAdapter(
        fail_script={"k": [TransientHbysError("t")] * 5}
    )
    with pytest.raises(TransientHbysError):
        sync_booking_with_retry(adapter, _req(key="k"), max_attempts=3)
    assert adapter.create_calls == 3


def test_permanent_error_is_not_retried():
    adapter = InMemoryHbysAdapter(fail_script={"k": [PermanentHbysError("bad")]})
    with pytest.raises(PermanentHbysError):
        sync_booking_with_retry(adapter, _req(key="k"), max_attempts=3)
    assert adapter.create_calls == 1


def test_conflict_is_not_retried():
    adapter = InMemoryHbysAdapter()
    adapter.create_booking(_req(key="a", doctor="D-1", hour=10))
    overlap = BookingRequest("b", "P-2", "D-1", datetime(2026, 8, 1, 10, 10), 30)
    with pytest.raises(SlotConflictError):
        sync_booking_with_retry(adapter, overlap, max_attempts=3)
    # SlotConflictError kalıcıdır → tek deneme (mevcut 1 + bu 1 = 2 create çağrısı).
    assert adapter.create_calls == 2


def test_invalid_max_attempts_rejected():
    adapter = InMemoryHbysAdapter()
    with pytest.raises(ValueError):
        sync_booking_with_retry(adapter, _req(), max_attempts=0)


# ── Saga / rollback ──────────────────────────────────────────────────────────


def test_all_procedures_written_on_success():
    adapter = InMemoryHbysAdapter()
    written = []
    result = book_with_procedures(
        adapter,
        _req(key="ok"),
        [ProcedureStep("Muayene"), ProcedureStep("Temizlik")],
        procedure_writer=lambda r, s: written.append(s.name),
    )
    assert result.status == "confirmed"
    assert written == ["Muayene", "Temizlik"]
    assert len(adapter.active_bookings()) == 1


def test_partial_failure_rolls_back_booking():
    adapter = InMemoryHbysAdapter()

    def writer(result, step):
        if step.name == "Dolgu":
            raise RuntimeError("boom")

    from app.integrations.hbys import HbysError

    with pytest.raises(HbysError):
        book_with_procedures(
            adapter,
            _req(key="saga"),
            [ProcedureStep("Muayene"), ProcedureStep("Dolgu")],
            procedure_writer=writer,
        )
    assert len(adapter.active_bookings()) == 0
    assert adapter.cancel_calls == 1


# ── find / cancel ────────────────────────────────────────────────────────────


def test_find_booking_returns_none_when_absent():
    adapter = InMemoryHbysAdapter()
    assert adapter.find_booking("nope") is None


def test_cancel_unknown_ref_raises():
    adapter = InMemoryHbysAdapter()
    with pytest.raises(PermanentHbysError):
        adapter.cancel_booking("HBYS-999999")


# ── Rapor ────────────────────────────────────────────────────────────────────


def test_report_all_gates_pass():
    report = build_report()
    for key, gate in report["gates"].items():
        assert gate["pass"], f"kapı düştü: {key} → {gate}"
    assert report["overall_pass"] is True
    assert report["remaining"]


def test_report_is_deterministic():
    a = json.dumps(build_report(), ensure_ascii=False, sort_keys=True)
    b = json.dumps(build_report(), ensure_ascii=False, sort_keys=True)
    assert a == b


def test_committed_artifact_is_fresh():
    committed = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    assert committed == build_report()


def test_cli_smoke_exits_zero():
    proc = subprocess.run(
        [sys.executable, "-m", "app.integrations.hbys", "--no-save", "--json"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["overall_pass"] is True
