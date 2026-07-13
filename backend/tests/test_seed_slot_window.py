"""Kayan pencere slot seed'i (ensure_doctor_slot_window).

Değişmezler:
- Slotlar İstanbul mesaisinde üretilir (09:00–17:00, öğle arası hariç).
- Pazar günü slot üretilmez.
- Gün bazında idempotent: ikinci koşu mevcut günlere dokunmaz.
- Var olan hekim için de pencere tamamlanır (eski kurulum self-heal).
"""
from __future__ import annotations

from datetime import date, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.models import ClinicDoctor, ClinicDoctorSlot
from app.seed.data import ensure_doctor_slot_window
from app.services.clinical_service import ensure_default_clinic

ISTANBUL = ZoneInfo("Europe/Istanbul")


def _make_doctor(db, clinic) -> ClinicDoctor:
    doctor = ClinicDoctor(
        clinic_id=clinic.id,
        full_name="Dr. Pencere Test",
        email="pencere@clinic.test",
        specialty="Diş Hekimliği",
        title="Dr.",
        is_active=True,
    )
    db.add(doctor)
    db.commit()
    db.refresh(doctor)
    return doctor


def _slots(db, doctor) -> list[ClinicDoctorSlot]:
    return list(
        db.scalars(
            select(ClinicDoctorSlot)
            .where(ClinicDoctorSlot.doctor_id == doctor.id)
            .order_by(ClinicDoctorSlot.start_time)
        )
    )


def test_slots_are_within_istanbul_business_hours(db_session):
    clinic = ensure_default_clinic(db_session)
    doctor = _make_doctor(db_session, clinic)
    created = ensure_doctor_slot_window(db_session, clinic, doctor, days=3)
    db_session.commit()
    assert created > 0

    for slot in _slots(db_session, doctor):
        local = slot.start_time.replace(tzinfo=timezone.utc).astimezone(ISTANBUL)
        assert 9 <= local.hour < 17, f"mesai dışı slot: {local}"
        # Öğle arası başlangıçları yok
        assert not (local.hour == 12 and local.minute == 30)
        assert not (local.hour == 13 and local.minute == 0)
        assert local.weekday() != 6, "pazar günü slot üretilmemeli"


def test_window_is_idempotent_per_day(db_session):
    clinic = ensure_default_clinic(db_session)
    doctor = _make_doctor(db_session, clinic)
    first = ensure_doctor_slot_window(db_session, clinic, doctor, days=3)
    db_session.commit()
    second = ensure_doctor_slot_window(db_session, clinic, doctor, days=3)
    db_session.commit()
    assert first > 0
    assert second == 0, "ikinci koşu hiçbir slot eklememeli"
    assert len(_slots(db_session, doctor)) == first


def test_window_tops_up_missing_days_for_existing_doctor(db_session):
    """Eski kurulum senaryosu: hekim var, takvimi yok → pencere tamamlanır."""
    clinic = ensure_default_clinic(db_session)
    doctor = _make_doctor(db_session, clinic)
    assert _slots(db_session, doctor) == []

    created = ensure_doctor_slot_window(db_session, clinic, doctor, days=2)
    db_session.commit()
    assert created > 0

    # Pencere kayınca (days=4) yalnız YENİ günler eklenir, eski günler çiftlenmez.
    added = ensure_doctor_slot_window(db_session, clinic, doctor, days=4)
    db_session.commit()
    slots = _slots(db_session, doctor)
    starts = [s.start_time for s in slots]
    assert len(starts) == len(set(starts)), "çift slot üretilmemeli"
    assert len(slots) == created + added


def test_full_window_covers_only_future_week(db_session):
    clinic = ensure_default_clinic(db_session)
    doctor = _make_doctor(db_session, clinic)
    ensure_doctor_slot_window(db_session, clinic, doctor, days=7)
    db_session.commit()
    slots = _slots(db_session, doctor)
    dates = {s.start_time.replace(tzinfo=timezone.utc).astimezone(ISTANBUL).date() for s in slots}
    assert min(dates) >= date.today()
    assert max(dates) <= date.today() + timedelta(days=6)
