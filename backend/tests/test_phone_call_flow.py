from sqlalchemy import select

from app.models import (
    ClinicalModelFeedback,
    ConsentRecord,
    ConsentType,
    ClinicConversation,
    ClinicMembership,
    ClinicMessage,
    ClinicMessageSender,
    ClinicUserRole,
    Doctor,
    ShadowReview,
    User,
)
from app.services.clinical_service import ensure_default_clinic


def test_phone_call_persists_multiturn_patient_for_doctor_and_feedback(
    client, db_session
):
    clinic = ensure_default_clinic(db_session)
    clinician = db_session.query(User).filter_by(email="operator@test.com").one()
    membership = db_session.scalars(
        select(ClinicMembership).where(
            ClinicMembership.clinic_id == clinic.id,
            ClinicMembership.user_id == clinician.id,
        )
    ).first()
    created_membership = membership is None
    original_membership_role = membership.role if membership is not None else None
    if membership is None:
        membership = ClinicMembership(clinic_id=clinic.id, user_id=clinician.id)
        db_session.add(membership)
    membership.role = ClinicUserRole.CLINICIAN
    doctor = Doctor(
        clinic_id=clinic.id,
        user_id=clinician.id,
        full_name=clinician.full_name,
        specialty="Genel Diş Hekimliği",
        is_active=True,
    )
    db_session.add(doctor)
    db_session.commit()

    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    first_turn = client.post(
        "/api/webhooks/voice/gather",
        headers=headers,
        data={
            "From": "+905557001122",
            "CallSid": "CA-phone-flow-001",
            "SpeechResult": "Dişim çok ağrıyor ve yüzüm şişti, yarın gelebilir miyim?",
        },
    )
    second_turn = client.post(
        "/api/webhooks/voice/gather",
        headers=headers,
        data={
            "From": "+905557001122",
            "CallSid": "CA-phone-flow-001",
            "SpeechResult": "Şimdi nefes almakta da zorlanıyorum.",
        },
    )

    assert first_turn.status_code == 200
    assert second_turn.status_code == 200
    assert "<Gather" in second_turn.text
    assert "112" in second_turn.text or "doktor ekranına" in second_turn.text

    conversations = list(
        db_session.scalars(
            select(ClinicConversation).where(
                ClinicConversation.clinic_id == clinic.id,
                ClinicConversation.external_thread_id == "CA-phone-flow-001",
            )
        )
    )
    assert len(conversations) == 1
    conversation = conversations[0]
    patient_turns = list(
        db_session.scalars(
            select(ClinicMessage).where(
                ClinicMessage.conversation_id == conversation.id,
                ClinicMessage.sender == ClinicMessageSender.PATIENT,
            )
        )
    )
    assert len(patient_turns) == 2
    assert len({message.external_message_id for message in patient_turns}) == 2
    pending_consent = db_session.scalars(
        select(ConsentRecord).where(
            ConsentRecord.conversation_id == conversation.id,
            ConsentRecord.consent_type == ConsentType.DATA_PROCESSING,
        )
    ).one()
    assert pending_consent.granted is False

    status_callback = client.post(
        "/api/webhooks/voice/status",
        headers=headers,
        data={
            "CallSid": "CA-phone-flow-001",
            "CallStatus": "completed",
            "CallDuration": "83",
        },
    )
    assert status_callback.status_code == 200
    db_session.expire_all()
    conversation = db_session.get(ClinicConversation, conversation.id)
    assert conversation.metadata_json["voice_call"]["terminal"] is True
    assert conversation.metadata_json["voice_call"]["duration_seconds"] == 83

    review = db_session.scalars(
        select(ShadowReview)
        .where(ShadowReview.conversation_id == conversation.id)
        .order_by(ShadowReview.id.desc())
    ).first()
    assert review is not None
    review.assigned_doctor_id = doctor.id
    db_session.commit()

    login = client.post(
        "/api/auth/login",
        json={"email": "operator@test.com", "password": "password123"},
    )
    assert login.status_code == 200
    clinician_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    overview = client.get("/api/clinical/overview", headers=clinician_headers)
    assert overview.status_code == 200
    doctor_records = overview.json()["doctor_inbox"]
    assert any(
        item["id"] == conversation.id and item["patient"]["phone"] == "+905557001122"
        for item in doctor_records
    )

    corrected = "Bu belirtiler acil olabilir. Lütfen 112'yi arayın; kaydınızı doktor ekranına aldım."
    decision = client.patch(
        f"/api/clinical/shadow-reviews/{review.id}",
        headers=clinician_headers,
        json={"status": "edited", "final_reply": corrected},
    )
    assert decision.status_code == 200
    assert decision.json()["metadata_json"]["training_status"] == "pending_redaction"

    feedback = db_session.scalars(
        select(ClinicalModelFeedback).where(ClinicalModelFeedback.review_id == review.id)
    ).one()
    assert feedback.outcome == "edited"
    assert feedback.corrected_reply == corrected
    assert feedback.training_status == "pending_redaction"
    assert feedback.mismatch_json["segments"]

    # Session-scope test DB'sinde geçici hekim bağı sonraki atamaları etkilemesin.
    for assigned_review in db_session.scalars(
        select(ShadowReview).where(ShadowReview.assigned_doctor_id == doctor.id)
    ):
        assigned_review.assigned_doctor_id = None
    db_session.flush()
    db_session.delete(doctor)
    if created_membership:
        db_session.delete(membership)
    else:
        membership.role = original_membership_role
    db_session.commit()
