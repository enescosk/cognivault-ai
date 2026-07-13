"""Gerçek takvim (ClinicDoctorSlot) → hasta slot teklifleri entegrasyonu.

Değişmezler:
- Klinik takviminde boş slot varsa teklifler ORADAN gelir (hayalî DEMO_SLOTS değil).
- Uzmanlığı eşleşen hekim önceliklidir; geçmiş/bloke/rezerve slot asla önerilmez.
- Onay gerçek slotu kilitler (is_booked); dolmuş slota ikinci onay 409'dur.
- Gerçek takvim boşsa davranışı `clinical_demo_slots_enabled` belirler.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.models import ClinicDoctor, ClinicDoctorSlot, ClinicalAppointment
from app.services.clinical_service import ensure_default_clinic
from tests.test_public_patient_scheduling import _bootstrap_public_session


@pytest.fixture()
def demo_flag():
    s = get_settings()
    original = s.clinical_demo_slots_enabled
    yield s
    s.clinical_demo_slots_enabled = original


def _add_doctor(db, clinic, *, name: str, specialty: str) -> ClinicDoctor:
    doctor = ClinicDoctor(
        clinic_id=clinic.id,
        full_name=name,
        email=f"{name.lower().replace(' ', '.')}@clinic.test",
        specialty=specialty,
        title="Dr.",
        is_active=True,
    )
    db.add(doctor)
    db.commit()
    db.refresh(doctor)
    return doctor


def _add_slot(db, clinic, doctor, *, hours_ahead: float, booked: bool = False, blocked: bool = False) -> ClinicDoctorSlot:
    start = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=hours_ahead)
    slot = ClinicDoctorSlot(
        clinic_id=clinic.id,
        doctor_id=doctor.id,
        start_time=start,
        end_time=start + timedelta(minutes=30),
        is_booked=booked,
        is_blocked=blocked,
    )
    db.add(slot)
    db.commit()
    db.refresh(slot)
    return slot


def _request_offers(client, db_session):
    slug, token, conversation_id = _bootstrap_public_session(client, db_session)
    res = client.post(
        f"/api/public/clinics/{slug}/conversations/{conversation_id}/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"body": "Dişim ağrıyor, randevu almak istiyorum"},
    )
    assert res.status_code == 200
    return slug, token, conversation_id, res.json()


def test_offers_come_from_real_calendar_when_slots_exist(client, db_session):
    clinic = ensure_default_clinic(db_session)
    doctor = _add_doctor(db_session, clinic, name="Ece Real", specialty="Diş Hekimliği")
    late = _add_slot(db_session, clinic, doctor, hours_ahead=30)
    early = _add_slot(db_session, clinic, doctor, hours_ahead=25)

    _slug, _token, _cid, data = _request_offers(client, db_session)
    offers = data["slot_offers"]
    assert offers, data
    metas = [o["metadata_json"] for o in offers]
    assert all(m.get("clinic_doctor_slot_id") for m in metas), "teklifler gerçek takvimden gelmeli"
    # Kronolojik: erken slot önce
    slot_ids = [m["clinic_doctor_slot_id"] for m in metas]
    assert slot_ids.index(early.id) < slot_ids.index(late.id)
    assert offers[0]["physician_name"] == "Dr. Ece Real"


def test_specialty_matching_prefers_department_doctor(client, db_session):
    clinic = ensure_default_clinic(db_session)
    derm = _add_doctor(db_session, clinic, name="Derma Doc", specialty="Dermatoloji")
    dental = _add_doctor(db_session, clinic, name="Dis Doc", specialty="Diş Hekimliği")
    _add_slot(db_session, clinic, derm, hours_ahead=20)  # daha erken ama yanlış branş
    dental_slot = _add_slot(db_session, clinic, dental, hours_ahead=26)

    _slug, _token, _cid, data = _request_offers(client, db_session)
    offers = data["slot_offers"]
    assert offers
    # "Genel Diş Hekimliği" talebi → Diş Hekimliği uzmanı; dermatolog daha erken olsa bile seçilmez.
    assert offers[0]["metadata_json"]["clinic_doctor_slot_id"] == dental_slot.id
    assert all(o["metadata_json"]["doctor_specialty"] == "Diş Hekimliği" for o in offers)


def test_booked_blocked_and_past_slots_never_offered(client, db_session):
    clinic = ensure_default_clinic(db_session)
    doctor = _add_doctor(db_session, clinic, name="Dis Doc", specialty="Diş Hekimliği")
    _add_slot(db_session, clinic, doctor, hours_ahead=24, booked=True)
    _add_slot(db_session, clinic, doctor, hours_ahead=25, blocked=True)
    _add_slot(db_session, clinic, doctor, hours_ahead=-2)  # geçmiş
    free = _add_slot(db_session, clinic, doctor, hours_ahead=26)

    _slug, _token, _cid, data = _request_offers(client, db_session)
    offers = data["slot_offers"]
    real_ids = [o["metadata_json"].get("clinic_doctor_slot_id") for o in offers]
    assert real_ids == [free.id]


def test_empty_calendar_falls_back_to_demo_when_enabled(client, db_session, demo_flag):
    demo_flag.clinical_demo_slots_enabled = True
    _slug, _token, _cid, data = _request_offers(client, db_session)
    offers = data["slot_offers"]
    assert offers, "demo modda boş takvimde bile teklif üretilmeli"
    assert all(not o["metadata_json"].get("clinic_doctor_slot_id") for o in offers)


def test_empty_calendar_yields_no_offers_in_pilot_mode(client, db_session, demo_flag):
    demo_flag.clinical_demo_slots_enabled = False
    _slug, _token, _cid, data = _request_offers(client, db_session)
    assert data["slot_offers"] == []


def test_confirm_books_real_slot_and_prevents_double_booking(client, db_session):
    clinic = ensure_default_clinic(db_session)
    doctor = _add_doctor(db_session, clinic, name="Dis Doc", specialty="Diş Hekimliği")
    slot = _add_slot(db_session, clinic, doctor, hours_ahead=26)

    slug, token, conversation_id, data = _request_offers(client, db_session)
    offer = data["slot_offers"][0]
    assert offer["metadata_json"]["clinic_doctor_slot_id"] == slot.id

    hold = client.post(
        f"/api/public/clinics/{slug}/conversations/{conversation_id}/slot-offers/{offer['id']}/hold",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert hold.status_code == 200

    confirm = client.post(
        f"/api/public/clinics/{slug}/conversations/{conversation_id}/appointments",
        headers={"Authorization": f"Bearer {token}"},
        json={"department": offer["department"], "slot_offer_id": offer["id"]},
    )
    assert confirm.status_code == 200

    db_session.expire_all()
    booked = db_session.get(ClinicDoctorSlot, slot.id)
    assert booked.is_booked is True
    appointment = db_session.scalars(
        select(ClinicalAppointment).order_by(ClinicalAppointment.id.desc())
    ).first()
    assert appointment.slot_id == slot.id
    assert appointment.doctor_id == doctor.id

    # İkinci hasta aynı alttaki slotu (bu arada dolmuş) onaylamaya çalışırsa 409.
    slug2, token2, cid2, data2 = _request_offers(client, db_session)
    # Takvimdeki tek slot artık dolu → teklif ya demo'dan gelir ya hiç gelmez;
    # dolmuş gerçek slot teklif edilmemeli.
    for o in data2["slot_offers"]:
        assert o["metadata_json"].get("clinic_doctor_slot_id") != slot.id


def test_stale_offer_on_booked_slot_conflicts_at_confirm(client, db_session):
    """Teklif üretildikten SONRA slot başka kanaldan dolarsa onay 409 olmalı."""
    clinic = ensure_default_clinic(db_session)
    doctor = _add_doctor(db_session, clinic, name="Dis Doc", specialty="Diş Hekimliği")
    slot = _add_slot(db_session, clinic, doctor, hours_ahead=26)

    slug, token, conversation_id, data = _request_offers(client, db_session)
    offer = data["slot_offers"][0]
    hold = client.post(
        f"/api/public/clinics/{slug}/conversations/{conversation_id}/slot-offers/{offer['id']}/hold",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert hold.status_code == 200

    # Operatör slotu manuel doldurdu (başka kanal)
    slot_row = db_session.get(ClinicDoctorSlot, slot.id)
    slot_row.is_booked = True
    db_session.add(slot_row)
    db_session.commit()

    confirm = client.post(
        f"/api/public/clinics/{slug}/conversations/{conversation_id}/appointments",
        headers={"Authorization": f"Bearer {token}"},
        json={"department": offer["department"], "slot_offer_id": offer["id"]},
    )
    assert confirm.status_code == 409
    assert confirm.json()["detail"] == "slot_already_booked"
