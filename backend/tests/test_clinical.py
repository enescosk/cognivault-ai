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
