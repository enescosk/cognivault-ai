from __future__ import annotations

from app.models import (
    ClinicalAppointment,
    ClinicalSlotOffer,
    ClinicalSlotOfferStatus,
    ConsentRecord,
    ConsentType,
    Doctor,
    User,
)
from app.services import patient_session
from app.services.clinical_service import ensure_default_clinic


def _bootstrap_public_session(
    client,
    db_session,
    phone: str = "+90 555 700 10 10",
    *,
    accepted_cross_border: bool = False,
    accepted_voice_processing: bool = False,
) -> tuple[str, str, int]:
    clinic = ensure_default_clinic(db_session)
    slug = clinic.slug
    disclosure = client.get(f"/api/public/clinics/{slug}/disclosure").json()

    consent_res = client.post(
        f"/api/public/clinics/{slug}/consent",
        json={
            "disclosure_version": disclosure["version"],
            "disclosure_hash": disclosure["body_hash"],
            "accepted_cross_border": accepted_cross_border,
            "accepted_voice_processing": accepted_voice_processing,
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


def test_public_voice_synthesis_uses_session_voice_consent(client, db_session, monkeypatch):
    clinic = ensure_default_clinic(db_session)
    clinic.settings_json = {**(clinic.settings_json or {}), "allow_cross_border_processors": True}
    db_session.add(clinic)
    db_session.commit()

    slug, session_token, conversation_id = _bootstrap_public_session(
        client,
        db_session,
        "+90 555 700 11 10",
        accepted_cross_border=True,
        accepted_voice_processing=True,
    )

    voice_consent = db_session.query(ConsentRecord).filter_by(
        conversation_id=conversation_id,
        consent_type=ConsentType.VOICE_RECORDING,
        withdrawn_at=None,
    ).first()
    assert voice_consent is not None

    captured: list[tuple[bool, bool]] = []

    class _FakeTTS:
        def synthesize(self, text: str, voice: str | None = None) -> tuple[bytes, str]:
            return b"RIFFfake-wave", "audio/wav"

    def fake_get_tts_provider(external_transfer_allowed=False, *, consent_granted=False, **_kwargs):
        captured.append((external_transfer_allowed, consent_granted))
        return _FakeTTS()

    from app.api.routes import public as public_routes

    monkeypatch.setattr(public_routes, "get_tts_provider", fake_get_tts_provider)
    res = client.post(
        f"/api/public/clinics/{slug}/voice/synthesize",
        headers={"Authorization": f"Bearer {session_token}"},
        json={"text": "Merhaba, size nasıl yardımcı olabilirim?", "voice": "nova"},
    )
    assert res.status_code == 200, res.text
    assert captured == [(True, True)]


def test_public_voice_synthesis_stays_local_without_voice_consent(client, db_session, monkeypatch):
    clinic = ensure_default_clinic(db_session)
    clinic.settings_json = {**(clinic.settings_json or {}), "allow_cross_border_processors": True}
    db_session.add(clinic)
    db_session.commit()

    slug, session_token, _conversation_id = _bootstrap_public_session(
        client,
        db_session,
        "+90 555 700 11 11",
        accepted_cross_border=True,
        accepted_voice_processing=False,
    )

    captured: list[tuple[bool, bool]] = []

    class _FakeTTS:
        def synthesize(self, text: str, voice: str | None = None) -> tuple[bytes, str]:
            return b"RIFFfake-wave", "audio/wav"

    def fake_get_tts_provider(external_transfer_allowed=False, *, consent_granted=False, **_kwargs):
        captured.append((external_transfer_allowed, consent_granted))
        return _FakeTTS()

    from app.api.routes import public as public_routes

    monkeypatch.setattr(public_routes, "get_tts_provider", fake_get_tts_provider)
    res = client.post(
        f"/api/public/clinics/{slug}/voice/synthesize",
        headers={"Authorization": f"Bearer {session_token}"},
        json={"text": "Merhaba", "voice": "nova"},
    )
    assert res.status_code == 200, res.text
    assert captured == [(True, False)]


def test_public_voice_transcript_metadata_is_returned_and_stored(client, db_session, monkeypatch):
    slug, session_token, conversation_id = _bootstrap_public_session(
        client,
        db_session,
        "+90 555 700 11 12",
    )

    class _FakeSTT:
        def transcribe(self, audio: bytes, language: str = "tr") -> str:
            assert audio == b"fake-audio"
            assert language == "tr"
            return "Diş ağrım var"

    def fake_get_stt_provider(external_transfer_allowed=False, *, consent_granted=False, **_kwargs):
        assert external_transfer_allowed is False
        assert consent_granted is False
        return _FakeSTT()

    from app.api.routes import public as public_routes

    monkeypatch.setattr(public_routes, "get_stt_provider", fake_get_stt_provider)
    transcribe = client.post(
        f"/api/public/clinics/{slug}/voice/transcribe?language=tr",
        headers={"Authorization": f"Bearer {session_token}"},
        files={"file": ("speech.webm", b"fake-audio", "audio/webm")},
    )
    assert transcribe.status_code == 200, transcribe.text
    voice_meta = transcribe.json()
    assert voice_meta["text"] == "Diş ağrım var"
    assert voice_meta["provider"] == "_FakeSTT"
    assert voice_meta["audio_bytes"] == len(b"fake-audio")
    assert voice_meta["processing_ms"] >= 0
    assert voice_meta["duration_seconds"] is None

    message = client.post(
        f"/api/public/clinics/{slug}/conversations/{conversation_id}/messages",
        headers={"Authorization": f"Bearer {session_token}"},
        json={
            "body": "Diş ağrım var",
            "voice_metadata": {
                "provider": voice_meta["provider"],
                "language": voice_meta["language"],
                "audio_bytes": voice_meta["audio_bytes"],
                "confidence": voice_meta["confidence"],
                "duration_seconds": voice_meta["duration_seconds"],
                "processing_ms": voice_meta["processing_ms"],
                "source": "voice_call",
            },
        },
    )
    assert message.status_code == 200, message.text
    patient_meta = message.json()["patient_message"]["metadata_json"]
    assert patient_meta["voice_transcript"]["transcript"] == "Diş ağrım var"
    assert patient_meta["voice_transcript"]["provider"] == "_FakeSTT"
    assert patient_meta["voice_transcript"]["processing_ms"] >= 0

    from app.models import ClinicConversation

    conversation = db_session.get(ClinicConversation, conversation_id)
    assert conversation is not None
    assert conversation.metadata_json["last_voice_transcript"]["provider"] == "_FakeSTT"


def test_public_voice_events_are_scoped_and_counted(client, db_session):
    slug, session_token, conversation_id = _bootstrap_public_session(
        client,
        db_session,
        "+90 555 700 11 13",
    )

    event = client.post(
        f"/api/public/clinics/{slug}/conversations/{conversation_id}/voice-events",
        headers={"Authorization": f"Bearer {session_token}"},
        json={
            "event_type": "no_result",
            "reason": "initial_silence",
            "retry_count": 1,
            "step": "complaint",
            "phase": "listening",
        },
    )
    assert event.status_code == 200, event.text
    assert event.json()["counters"]["no_result"] == 1
    assert event.json()["counters"]["no_result:initial_silence"] == 1

    retry = client.post(
        f"/api/public/clinics/{slug}/conversations/{conversation_id}/voice-events",
        headers={"Authorization": f"Bearer {session_token}"},
        json={"event_type": "retry_prompt", "reason": "no_result", "retry_count": 1},
    )
    assert retry.status_code == 200, retry.text

    from app.models import ClinicConversation

    conversation = db_session.get(ClinicConversation, conversation_id)
    assert conversation is not None
    counters = conversation.metadata_json["voice_event_counters"]
    assert counters["no_result"] == 1
    assert counters["retry_prompt"] == 1
    assert counters["max_retry_count"] == 1
    assert conversation.metadata_json["last_voice_event"]["event_type"] == "retry_prompt"


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
    clinic = ensure_default_clinic(db_session)
    operator = db_session.query(User).filter_by(email="operator@test.com").first()
    linked_doctor = db_session.query(Doctor).filter_by(user_id=operator.id).first()
    if linked_doctor is None:
        linked_doctor = Doctor(
            clinic_id=clinic.id,
            user_id=operator.id,
            full_name=offer["physician_name"],
            specialty=offer["department"],
            is_active=True,
        )
    else:
        linked_doctor.full_name = offer["physician_name"]
        linked_doctor.specialty = offer["department"]
    db_session.add(linked_doctor)
    db_session.commit()
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


def test_pilot_metrics_reflect_public_voice_booking(client, db_session, operator_token):
    slug, session_token, conversation_id = _bootstrap_public_session(
        client, db_session, "+90 555 700 33 23"
    )
    message = client.post(
        f"/api/public/clinics/{slug}/conversations/{conversation_id}/messages",
        headers={"Authorization": f"Bearer {session_token}"},
        json={
            "body": "Diş ağrım var, yarın randevu almak istiyorum.",
            "voice_metadata": {
                "provider": "FakeSTT",
                "language": "tr",
                "audio_bytes": 4096,
                "confidence": 0.86,
                "duration_seconds": 3.2,
                "processing_ms": 480,
                "source": "voice_call",
            },
        },
    )
    assert message.status_code == 200, message.text
    offer = message.json()["slot_offers"][0]

    hold = client.post(
        f"/api/public/clinics/{slug}/conversations/{conversation_id}/slot-offers/{offer['id']}/hold",
        headers={"Authorization": f"Bearer {session_token}"},
    )
    assert hold.status_code == 200, hold.text
    confirm = client.post(
        f"/api/public/clinics/{slug}/conversations/{conversation_id}/appointments",
        headers={"Authorization": f"Bearer {session_token}"},
        json={"department": offer["department"], "slot_offer_id": offer["id"]},
    )
    assert confirm.status_code == 200, confirm.text

    metrics = client.get(
        "/api/clinical/pilot-metrics",
        headers={"Authorization": f"Bearer {operator_token}"},
    )
    assert metrics.status_code == 200, metrics.text
    payload = metrics.json()
    by_id = {item["id"]: item for item in payload["metrics"]}
    assert payload["totals"]["conversations"] >= 1
    assert payload["totals"]["successful_appointments"] >= 1
    assert payload["totals"]["voice_messages"] >= 1
    assert by_id["booking_success_rate"]["value"] > 0
    assert by_id["under_60_second_booking_rate"]["value"] > 0
    assert by_id["voice_stt_confidence"]["value"] >= 80
    assert by_id["emergency_safety_incidents"]["value"] == 0


def test_pilot_metrics_include_voice_retry_and_failure_events(client, db_session, operator_token):
    slug, session_token, conversation_id = _bootstrap_public_session(
        client, db_session, "+90 555 700 33 24"
    )
    for payload in [
        {"event_type": "no_result", "reason": "too_short", "retry_count": 1},
        {"event_type": "retry_prompt", "reason": "no_result", "retry_count": 1},
        {"event_type": "stt_failure", "reason": "provider_error", "retry_count": 1},
    ]:
        res = client.post(
            f"/api/public/clinics/{slug}/conversations/{conversation_id}/voice-events",
            headers={"Authorization": f"Bearer {session_token}"},
            json=payload,
        )
        assert res.status_code == 200, res.text

    metrics = client.get(
        "/api/clinical/pilot-metrics",
        headers={"Authorization": f"Bearer {operator_token}"},
    )
    assert metrics.status_code == 200, metrics.text
    payload = metrics.json()
    by_id = {item["id"]: item for item in payload["metrics"]}
    assert payload["totals"]["voice_no_result_events"] >= 1
    assert payload["totals"]["voice_stt_failure_events"] >= 1
    assert by_id["voice_no_result_rate"]["value"] > 0
    assert by_id["voice_retry_prompt_rate"]["value"] > 0
    assert by_id["voice_stt_failures"]["value"] >= 1


def test_operator_can_create_manual_appointment_from_slot(client, db_session, operator_token):
    """Operatör slot panosundan sohbet olmadan randevu açabilir; liste zenginleştirilmiş döner."""
    ensure_default_clinic(db_session)
    auth = {"Authorization": f"Bearer {operator_token}"}
    res = client.post(
        "/api/clinical/appointments/manual",
        headers=auth,
        json={
            "full_name": "Manuel Hasta",
            "phone": "+90 555 700 44 11",
            "department": "Endodonti",
            "starts_at": "2026-06-08T09:30:00",
            "physician_name": "Dr. Selin Okan",
            "branch_name": "Bahçelievler",
            "notes": "Slot panosundan açıldı",
        },
    )
    assert res.status_code == 200, res.text
    row = res.json()
    assert row["patient_name"] == "Manuel Hasta"
    assert row["patient_phone"]
    assert row["physician_name"] == "Dr. Selin Okan"
    assert row["status"] == "pending"
    assert row["conversation_id"] is None

    listing = client.get("/api/clinical/appointments", headers=auth).json()
    assert any(item["id"] == row["id"] for item in listing)


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
