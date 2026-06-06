from __future__ import annotations

from app.models import ClinicalAppointment, ClinicalSlotOffer, ClinicalSlotOfferStatus, ConsentRecord
from app.services import patient_session
from app.services.clinical_service import ensure_default_clinic


def _bootstrap_public_session(client, db_session, phone: str = "+90 555 700 10 10") -> tuple[str, str, int]:
    clinic = ensure_default_clinic(db_session)
    slug = clinic.slug
    disclosure = client.get(f"/api/public/clinics/{slug}/disclosure").json()

    consent_res = client.post(
        f"/api/public/clinics/{slug}/consent",
        json={
            "disclosure_version": disclosure["version"],
            "disclosure_hash": disclosure["body_hash"],
            "accepted_cross_border": False,
        },
    )
    assert consent_res.status_code == 200
    consent_token = consent_res.json()["consent_token"]

    start_res = client.post(
        f"/api/public/clinics/{slug}/conversations",
        headers={"Authorization": f"Bearer {consent_token}"},
        json={"full_name": "Public Demo Hasta", "phone": phone},
    )
    assert start_res.status_code == 200
    data = start_res.json()
    return slug, data["session_token"], data["conversation_id"]


def test_public_patient_can_only_confirm_a_held_slot_offer(client, db_session):
    slug, session_token, conversation_id = _bootstrap_public_session(
        client, db_session, "+90 555 700 20 10"
    )

    message_res = client.post(
        f"/api/public/clinics/{slug}/conversations/{conversation_id}/messages",
        headers={"Authorization": f"Bearer {session_token}"},
        json={"body": "Dolgum düştü, bugün randevu almak istiyorum."},
    )
    assert message_res.status_code == 200
    message_data = message_res.json()
    assert message_data["slot_offers"], message_data

    offer = message_data["slot_offers"][0]
    premature_confirm = client.post(
        f"/api/public/clinics/{slug}/conversations/{conversation_id}/appointments",
        headers={"Authorization": f"Bearer {session_token}"},
        json={
            "department": offer["department"],
            "slot_offer_id": offer["id"],
            "notes": "premature",
        },
    )
    assert premature_confirm.status_code == 409
    assert premature_confirm.json()["detail"] == "slot_offer_must_be_held"

    hold_res = client.post(
        f"/api/public/clinics/{slug}/conversations/{conversation_id}/slot-offers/{offer['id']}/hold",
        headers={"Authorization": f"Bearer {session_token}"},
    )
    assert hold_res.status_code == 200
    assert hold_res.json()["slot_offer"]["status"] == "held"

    confirm_res = client.post(
        f"/api/public/clinics/{slug}/conversations/{conversation_id}/appointments",
        headers={"Authorization": f"Bearer {session_token}"},
        json={
            "department": offer["department"],
            "slot_offer_id": offer["id"],
            "notes": "Hasta web chat üzerinden onayladı.",
        },
    )
    assert confirm_res.status_code == 200
    confirm_data = confirm_res.json()
    assert confirm_data["starts_at"] == offer["starts_at"]
    assert confirm_data["department"] == offer["department"]

    appointment = db_session.get(ClinicalAppointment, confirm_data["appointment_id"])
    assert appointment is not None
    assert appointment.metadata_json["slot_offer_id"] == offer["id"]
    stored_offer = db_session.get(ClinicalSlotOffer, offer["id"])
    assert stored_offer is not None
    assert stored_offer.status == ClinicalSlotOfferStatus.CONSUMED


def test_operator_lists_and_confirms_patient_booked_appointment(client, db_session, operator_token):
    """Hasta sohbetten randevu alır (PENDING); operatör panelden görüp onaylar."""
    slug, session_token, conversation_id = _bootstrap_public_session(
        client, db_session, "+90 555 700 33 22"
    )
    message = client.post(
        f"/api/public/clinics/{slug}/conversations/{conversation_id}/messages",
        headers={"Authorization": f"Bearer {session_token}"},
        json={"body": "Dolgum düştü, bugün randevu almak istiyorum."},
    ).json()
    offer = message["slot_offers"][0]
    client.post(
        f"/api/public/clinics/{slug}/conversations/{conversation_id}/slot-offers/{offer['id']}/hold",
        headers={"Authorization": f"Bearer {session_token}"},
    )
    confirm = client.post(
        f"/api/public/clinics/{slug}/conversations/{conversation_id}/appointments",
        headers={"Authorization": f"Bearer {session_token}"},
        json={"department": offer["department"], "slot_offer_id": offer["id"]},
    ).json()
    appointment_id = confirm["appointment_id"]

    auth = {"Authorization": f"Bearer {operator_token}"}
    listing = client.get("/api/clinical/appointments", headers=auth)
    assert listing.status_code == 200
    rows = listing.json()
    target = next((row for row in rows if row["id"] == appointment_id), None)
    assert target is not None, rows
    assert target["patient_name"]  # zenginleştirilmiş hasta adı
    assert target["status"] == "pending"

    updated = client.post(
        f"/api/clinical/appointments/{appointment_id}/status",
        headers=auth,
        json={"status": "confirmed"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "confirmed"


def test_public_consent_token_binds_only_its_own_audit_rows(client, db_session):
    clinic = ensure_default_clinic(db_session)
    slug = clinic.slug
    disclosure = client.get(f"/api/public/clinics/{slug}/disclosure").json()

    consent_payload = {
        "disclosure_version": disclosure["version"],
        "disclosure_hash": disclosure["body_hash"],
        "accepted_cross_border": False,
    }
    first = client.post(f"/api/public/clinics/{slug}/consent", json=consent_payload).json()
    second = client.post(f"/api/public/clinics/{slug}/consent", json=consent_payload).json()
    first_payload = patient_session.decode_consent_token(first["consent_token"])
    second_payload = patient_session.decode_consent_token(second["consent_token"])

    start_res = client.post(
        f"/api/public/clinics/{slug}/conversations",
        headers={"Authorization": f"Bearer {first['consent_token']}"},
        json={"full_name": "Audit Hasta", "phone": "+90 555 700 20 20"},
    )
    assert start_res.status_code == 200

    bound_rows = [
        db_session.get(ConsentRecord, consent_id)
        for consent_id in first_payload.consent_record_ids
    ]
    untouched_rows = [
        db_session.get(ConsentRecord, consent_id)
        for consent_id in second_payload.consent_record_ids
    ]
    assert all(row is not None and row.patient_id is not None for row in bound_rows)
    assert all(row is not None and row.patient_id is None for row in untouched_rows)
