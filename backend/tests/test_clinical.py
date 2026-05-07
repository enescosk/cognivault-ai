from datetime import datetime, timedelta, timezone


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


def test_appointment_draft_is_created_from_conversation_and_confirmed(client, operator_token):
    res = client.post(
        "/api/clinical/simulate-whatsapp",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={
            "from_phone": "+90 555 303 40 50",
            "patient_name": "Randevu Hasta",
            "body": "Yarin saat 10 dis tasi temizligi icin randevu almak istiyorum.",
        },
    )

    assert res.status_code == 200
    data = res.json()
    assert data["appointment_id"] is not None

    detail = client.get(
        f"/api/clinical/conversations/{data['conversation_id']}",
        headers={"Authorization": f"Bearer {operator_token}"},
    )
    assert detail.status_code == 200
    draft = detail.json()["appointment_draft"]
    assert draft["id"] == data["appointment_id"]
    assert draft["department"] == "Dis tasi temizligi"
    assert draft["status"] == "pending"

    starts_at = (datetime.now(timezone.utc) + timedelta(days=1)).replace(microsecond=0)
    confirmed = client.post(
        "/api/clinical/appointments",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={
            "conversation_id": data["conversation_id"],
            "department": draft["department"],
            "starts_at": starts_at.isoformat(),
            "notes": "Doktor onayi ile randevu kesinlestirildi.",
        },
    )

    assert confirmed.status_code == 200
    payload = confirmed.json()
    assert payload["id"] == data["appointment_id"]
    assert payload["status"] == "confirmed"


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


def test_symptom_triage_enriches_doctor_inbox_metadata(client, operator_token):
    res = client.post(
        "/api/clinical/simulate-voice-call",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={
            "from_phone": "+90 555 707 80 90",
            "patient_name": "Dis Agrisi Hasta",
            "speech": "Dis agrim ve sislik var, implant bolgesi de agriyor.",
            "persona_id": "can",
        },
    )

    assert res.status_code == 200
    data = res.json()
    assert data["action"] == "shadow_review"

    overview = client.get("/api/clinical/overview", headers={"Authorization": f"Bearer {operator_token}"})
    assert overview.status_code == 200
    payload = overview.json()
    review = next(item for item in payload["shadow_reviews"] if item["conversation_id"] == data["conversation_id"])
    triage = review["metadata_json"]["triage"]
    assert review["intent"] == "symptom_triage"
    assert triage["urgency"] in {"same_day", "soon"}
    assert triage["requires_doctor_review"] is True
    assert triage["possible_conditions"]
    assert triage["doctor_summary"]
    assert review["metadata_json"]["doctor_summary"]


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
