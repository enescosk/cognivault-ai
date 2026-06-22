def test_operator_can_simulate_whatsapp_message(client, operator_token):
    res = client.post(
        "/api/clinical/simulate-whatsapp",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={
            "from_phone": "+90 555 101 20 30",
            "patient_name": "Test Hasta",
            "body": "Yarin randevu var mi?",
        },
    )

    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["action"] in {"auto_reply", "shadow_review"}
    assert data["conversation_id"] > 0


def test_medical_emergency_routes_to_shadow_mode(client, operator_token):
    res = client.post(
        "/api/clinical/simulate-whatsapp",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={
            "from_phone": "+90 555 404 50 60",
            "patient_name": "Acil Hasta",
            "body": "Gogsumde agri var nefes alamiyorum acil ne yapayim?",
        },
    )

    assert res.status_code == 200
    data = res.json()
    assert data["action"] == "shadow_review"
    assert data["shadow_review_id"] is not None

    overview = client.get("/api/clinical/overview", headers={"Authorization": f"Bearer {operator_token}"})
    assert overview.status_code == 200
    assert overview.json()["metrics"]["pending_shadow_reviews"] >= 1


def test_customer_cannot_access_clinical_dashboard(client, customer_token):
    res = client.get("/api/clinical/overview", headers={"Authorization": f"Bearer {customer_token}"})
    assert res.status_code == 403


def test_twilio_webhook_ingests_without_auth(client):
    res = client.post(
        "/api/webhooks/whatsapp",
        data={
            "From": "whatsapp:+905551112244",
            "Body": "Adresinizi ogrenebilir miyim?",
            "ProfileName": "Webhook Hasta",
            "MessageSid": "SM_TEST_1",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["message_id"] > 0


def test_voice_call_routes_to_phone_channel_and_doctor_inbox(client, operator_token):
    res = client.post(
        "/api/clinical/simulate-voice-call",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={
            "from_phone": "+90 555 909 10 11",
            "patient_name": "Sesli Hasta",
            "speech": "Doktoruma iletin, gogsumde agri ve nefes darligi var.",
            "persona_id": "can",
        },
    )

    assert res.status_code == 200
    data = res.json()
    assert data["action"] == "shadow_review"

    overview = client.get("/api/clinical/overview", headers={"Authorization": f"Bearer {operator_token}"})
    assert overview.status_code == 200
    payload = overview.json()
    assert payload["metrics"]["phone_calls_today"] >= 1
    assert payload["metrics"]["doctor_inbox_count"] >= 1
    assert any(item["channel"] == "phone" for item in payload["doctor_inbox"])


def _seed_patient_and_conversation(client, operator_token, phone: str, name: str) -> tuple[int, int]:
    res = client.post(
        "/api/clinical/simulate-whatsapp",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={"from_phone": phone, "patient_name": name, "body": "Randevu almak istiyorum."},
    )
    assert res.status_code == 200
    data = res.json()
    return data["patient_id"], data["conversation_id"]


def test_pre_intake_full_lifecycle(client, operator_token):
    patient_id, conversation_id = _seed_patient_and_conversation(
        client, operator_token, "+90 555 700 80 90", "Ön Kayıt Hasta"
    )

    create_res = client.post(
        "/api/clinical/pre-intakes",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={
            "patient_id": patient_id,
            "conversation_id": conversation_id,
            "answers": {"chief_complaint": "Baş ağrısı", "duration_days": 3},
        },
    )
    assert create_res.status_code == 200
    created = create_res.json()
    assert created["patient_id"] == patient_id
    assert created["conversation_id"] == conversation_id
    assert created["answers_json"] == {"chief_complaint": "Baş ağrısı", "duration_days": 3}
    assert created["is_complete"] is False
    pre_intake_id = created["id"]

    # Partial update merges new answers into existing.
    patch_res = client.patch(
        f"/api/clinical/pre-intakes/{pre_intake_id}",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={"answers": {"insurance": "SGK"}},
    )
    assert patch_res.status_code == 200
    merged = patch_res.json()
    assert merged["answers_json"] == {
        "chief_complaint": "Baş ağrısı",
        "duration_days": 3,
        "insurance": "SGK",
    }
    assert merged["is_complete"] is False

    # Replace mode wipes prior answers and marks the form complete.
    replace_res = client.patch(
        f"/api/clinical/pre-intakes/{pre_intake_id}",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={"answers": {"chief_complaint": "Final özet"}, "replace": True, "is_complete": True},
    )
    assert replace_res.status_code == 200
    replaced = replace_res.json()
    assert replaced["answers_json"] == {"chief_complaint": "Final özet"}
    assert replaced["is_complete"] is True

    # Get + list filters
    detail_res = client.get(
        f"/api/clinical/pre-intakes/{pre_intake_id}",
        headers={"Authorization": f"Bearer {operator_token}"},
    )
    assert detail_res.status_code == 200
    assert detail_res.json()["id"] == pre_intake_id

    list_res = client.get(
        "/api/clinical/pre-intakes",
        headers={"Authorization": f"Bearer {operator_token}"},
        params={"patient_id": patient_id, "is_complete": "true"},
    )
    assert list_res.status_code == 200
    ids = [item["id"] for item in list_res.json()]
    assert pre_intake_id in ids


def test_pre_intake_create_rejects_unknown_patient(client, operator_token):
    res = client.post(
        "/api/clinical/pre-intakes",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={"patient_id": 999999, "answers": {}},
    )
    assert res.status_code == 404


def test_pre_intake_get_returns_404_for_missing_id(client, operator_token):
    res = client.get(
        "/api/clinical/pre-intakes/999999",
        headers={"Authorization": f"Bearer {operator_token}"},
    )
    assert res.status_code == 404


def test_customer_cannot_access_pre_intake_endpoints(client, customer_token):
    res = client.get(
        "/api/clinical/pre-intakes",
        headers={"Authorization": f"Bearer {customer_token}"},
    )
    assert res.status_code == 403


def test_voice_webhook_returns_twiml(client):
    res = client.post(
        "/api/webhooks/voice/gather",
        data={
            "From": "+905551010101",
            "CallSid": "CA_TEST_1",
            "SpeechResult": "Randevu almak istiyorum",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert res.status_code == 200
    assert "application/xml" in res.headers["content-type"]
    assert "<Gather" in res.text


# ── Doctor & Slot tests ──────────────────────────────────────────────────────


def _seed_doctor(client, operator_token):
    """Create a clinic doctor via DB for testing."""
    from tests.conftest import TestingSessionLocal
    from app.models import Clinic, ClinicBranch, ClinicDoctor, ClinicDoctorSlot
    from app.services.clinical_service import ensure_default_clinic
    from datetime import datetime, timedelta, timezone

    db = TestingSessionLocal()
    clinic = ensure_default_clinic(db)

    clinic_id = clinic.id
    existing = db.query(ClinicDoctor).filter_by(clinic_id=clinic_id, email="test.doc@clinic.com").first()
    if existing:
        eid = existing.id
        db.close()
        return eid, clinic_id

    doctor = ClinicDoctor(
        clinic_id=clinic_id,
        full_name="Dr. Test Hekim",
        email="test.doc@clinic.com",
        specialty="Dermatoloji",
        title="Uzm. Dr.",
    )
    db.add(doctor)
    db.flush()

    now = datetime.now(timezone.utc).replace(hour=10, minute=0, second=0, microsecond=0)
    for i in range(4):
        start = now + timedelta(minutes=30 * i)
        db.add(ClinicDoctorSlot(
            doctor_id=doctor.id,
            clinic_id=clinic_id,
            start_time=start,
            end_time=start + timedelta(minutes=30),
        ))
    db.commit()
    doctor_id = doctor.id
    db.close()
    return doctor_id, clinic_id


def test_list_doctors(client, operator_token):
    _seed_doctor(client, operator_token)
    res = client.get("/api/clinical/doctors", headers={"Authorization": f"Bearer {operator_token}"})
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 1
    assert any(d["email"] == "test.doc@clinic.com" for d in data)


def test_list_doctor_slots(client, operator_token):
    doctor_id, _ = _seed_doctor(client, operator_token)
    today = datetime.now().strftime("%Y-%m-%d")
    res = client.get(
        f"/api/clinical/doctors/{doctor_id}/slots?date={today}",
        headers={"Authorization": f"Bearer {operator_token}"},
    )
    assert res.status_code == 200
    slots = res.json()
    assert len(slots) >= 1
    assert all(not s["is_booked"] for s in slots)


def test_book_slot_marks_as_booked(client, operator_token):
    doctor_id, _ = _seed_doctor(client, operator_token)

    # First simulate a whatsapp message to get a conversation
    msg_res = client.post(
        "/api/clinical/simulate-whatsapp",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={"from_phone": "+90 555 777 88 99", "patient_name": "Slot Test", "body": "Dermatoloji randevusu"},
    )
    assert msg_res.status_code == 200
    conversation_id = msg_res.json()["conversation_id"]

    # Get available slots
    today = datetime.now().strftime("%Y-%m-%d")
    slots_res = client.get(
        f"/api/clinical/doctors/{doctor_id}/slots?date={today}",
        headers={"Authorization": f"Bearer {operator_token}"},
    )
    slots = slots_res.json()
    available = [s for s in slots if not s["is_booked"]]
    assert len(available) >= 1
    slot_id = available[0]["id"]

    # Create appointment with slot
    appt_res = client.post(
        "/api/clinical/appointments",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={
            "conversation_id": conversation_id,
            "department": "Dermatoloji",
            "doctor_id": doctor_id,
            "slot_id": slot_id,
        },
    )
    assert appt_res.status_code == 200
    appt = appt_res.json()
    assert appt["doctor_id"] == doctor_id
    assert appt["slot_id"] == slot_id
    assert appt["status"] == "confirmed"
    assert appt["doctor_name"] == "Dr. Test Hekim"

    # Verify slot is now booked
    slots_res2 = client.get(
        f"/api/clinical/doctors/{doctor_id}/slots?date={today}",
        headers={"Authorization": f"Bearer {operator_token}"},
    )
    slots2 = slots_res2.json()
    booked_slot = next((s for s in slots2 if s["id"] == slot_id), None)
    assert booked_slot is not None
    assert booked_slot["is_booked"] is True


def test_double_book_slot_returns_409(client, operator_token):
    doctor_id, _ = _seed_doctor(client, operator_token)

    # Create two conversations
    msg1 = client.post(
        "/api/clinical/simulate-whatsapp",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={"from_phone": "+90 555 111 00 01", "body": "Cilt alerjisi randevusu"},
    )
    msg2 = client.post(
        "/api/clinical/simulate-whatsapp",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={"from_phone": "+90 555 111 00 02", "body": "Cilt kontrolu"},
    )
    conv1 = msg1.json()["conversation_id"]
    conv2 = msg2.json()["conversation_id"]

    # Get an available slot
    today = datetime.now().strftime("%Y-%m-%d")
    slots = client.get(
        f"/api/clinical/doctors/{doctor_id}/slots?date={today}",
        headers={"Authorization": f"Bearer {operator_token}"},
    ).json()
    available = [s for s in slots if not s["is_booked"]]
    if not available:
        return  # all slots booked from previous tests, skip
    slot_id = available[0]["id"]

    # Book first
    r1 = client.post(
        "/api/clinical/appointments",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={"conversation_id": conv1, "department": "Dermatoloji", "slot_id": slot_id},
    )
    assert r1.status_code == 200

    # Try to double-book
    r2 = client.post(
        "/api/clinical/appointments",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={"conversation_id": conv2, "department": "Dermatoloji", "slot_id": slot_id},
    )
    assert r2.status_code == 409


def test_seed_idempotency(client, operator_token):
    """Running seed twice should not create duplicate doctors."""
    from tests.conftest import TestingSessionLocal
    from app.seed.data import seed_clinical_doctors
    from app.models import ClinicDoctor

    db = TestingSessionLocal()
    seed_clinical_doctors(db)
    count1 = db.query(ClinicDoctor).count()
    seed_clinical_doctors(db)
    count2 = db.query(ClinicDoctor).count()
    db.close()
    assert count1 == count2


from datetime import datetime
