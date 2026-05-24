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


def test_dental_pain_routes_to_appointment_intake_with_specialty(client, operator_token):
    res = client.post(
        "/api/clinical/simulate-voice-call",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={
            "from_phone": "+90 555 333 22 11",
            "patient_name": "Diş Hasta",
            "speech": "Arka dişim zonkluyor, yarın için diş hekimi randevusu almak istiyorum.",
            "persona_id": "selin",
        },
    )

    assert res.status_code == 200
    data = res.json()
    assert data["action"] in {"auto_reply", "shadow_review"}

    conversation = client.get(
        f"/api/clinical/conversations/{data['conversation_id']}",
        headers={"Authorization": f"Bearer {operator_token}"},
    )
    assert conversation.status_code == 200
    payload = conversation.json()
    assert payload["intent"] == "book_appointment"
    assert any(
        "Endodonti" in message["content"] and "plan görüntüleniyor" not in message["content"].lower()
        for message in payload["messages"]
        if message["sender"] in {"assistant", "operator"}
    ) or payload["status"] == "waiting_human"

    if payload["status"] == "waiting_human":
        overview = client.get("/api/clinical/overview", headers={"Authorization": f"Bearer {operator_token}"})
        reviews = overview.json()["shadow_reviews"]
        assert any(
            review["conversation_id"] == data["conversation_id"]
            and review["metadata_json"]["data"]["intake"]["specialty"] == "Endodonti"
            for review in reviews
        )


def test_clinical_compliance_profile_exposes_kvkk_controls(client, operator_token):
    res = client.get("/api/clinical/compliance-profile", headers={"Authorization": f"Bearer {operator_token}"})

    assert res.status_code == 200
    data = res.json()
    assert data["data_residency_default"] == "tr_local_first"
    assert data["external_transfer_allowed"] is False
    assert "special_category_data_safeguards" in data["mandatory_controls"]
    assert "cross_border_ai_processing_without_consent" in data["blocked_by_default"]
    assert "external_llm_for_special_category_health_data" in data["blocked_by_default"]
    assert all(item["allowed_for_clinical"] is False for item in data["processor_inventory"])


def test_insurance_lookup_requires_human_review_and_privacy_metadata(client, operator_token):
    res = client.post(
        "/api/clinical/simulate-whatsapp",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={
            "from_phone": "+90 555 606 70 80",
            "patient_name": "Sigorta Hasta",
            "body": "Kanal tedavisi icin sigortam karsilar mi? Kart numaram 4111 1111 1111 1111",
        },
    )

    assert res.status_code == 200
    data = res.json()
    assert data["action"] == "shadow_review"

    overview = client.get("/api/clinical/overview", headers={"Authorization": f"Bearer {operator_token}"})
    reviews = overview.json()["shadow_reviews"]
    review = next(item for item in reviews if item["conversation_id"] == data["conversation_id"])
    guardrail = review["metadata_json"]["data"]["privacy_guardrail"]
    assert "financial_or_insurance_data" in guardrail["data_classes"]
    assert "insurance_verification_requires_explicit_consent" in guardrail["human_review_reasons"]
    assert "[REDACTED]" in guardrail["redacted_preview"]


def test_clinical_patent_dossier_contains_claim_candidates(client, operator_token):
    res = client.get("/api/clinical/patent-dossier", headers={"Authorization": f"Bearer {operator_token}"})

    assert res.status_code == 200
    data = res.json()
    assert "KVKK-first" in data["working_title"]
    assert len(data["candidate_independent_claims"]) >= 3
    assert any("doctor approval packet" in claim for claim in data["candidate_independent_claims"])


def test_slot_board_exposes_full_slots_and_acceptance_rules(client, operator_token):
    res = client.get("/api/clinical/slot-board", headers={"Authorization": f"Bearer {operator_token}"})

    assert res.status_code == 200
    data = res.json()
    assert data["summary"]["full_departments"] >= 1
    assert any(slot["status"] == "full" for slot in data["schedule"])
    assert any("İstenen slot dolu" in item["rule"] for item in data["acceptance_rules"])
    assert any("Dolu slot" == item["label"] for item in data["test_scenarios"])


def test_full_slot_request_returns_alternative_slot_metadata(client, operator_token):
    res = client.post(
        "/api/clinical/simulate-voice-call",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={
            "from_phone": "+90 555 444 55 66",
            "patient_name": "Slot Hasta",
            "speech": "Yarın kanal tedavisi için randevu istiyorum.",
            "persona_id": "selin",
        },
    )

    assert res.status_code == 200
    data = res.json()
    conversation = client.get(
        f"/api/clinical/conversations/{data['conversation_id']}",
        headers={"Authorization": f"Bearer {operator_token}"},
    ).json()

    assistant_messages = [message for message in conversation["messages"] if message["sender"] == "assistant"]
    if assistant_messages:
        latest = assistant_messages[-1]
        assert "dolu" in latest["content"].lower()
        assert latest["metadata_json"]["data"]["slot_decision"]["status"] == "waitlist"
    else:
        overview = client.get("/api/clinical/overview", headers={"Authorization": f"Bearer {operator_token}"}).json()
        review = next(item for item in overview["shadow_reviews"] if item["conversation_id"] == data["conversation_id"])
        assert "dolu" in review["draft_reply"].lower()
        assert review["metadata_json"]["data"]["slot_decision"]["status"] in {"waitlist", "doctor_review"}


def test_dermatology_message_gets_safe_appointment_routing(client, operator_token):
    res = client.post(
        "/api/clinical/simulate-whatsapp",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={
            "from_phone": "+90 555 222 33 44",
            "patient_name": "Derm Hasta",
            "body": "Cildimde akne ve leke var, dermatoloji randevusu alabilir miyim?",
        },
    )

    assert res.status_code == 200
    data = res.json()
    conversation = client.get(
        f"/api/clinical/conversations/{data['conversation_id']}",
        headers={"Authorization": f"Bearer {operator_token}"},
    ).json()
    assert conversation["intent"] == "book_appointment"

    metadata_candidates = [
        message["metadata_json"]["data"]
        for message in conversation["messages"]
        if message["sender"] == "assistant" and message.get("metadata_json", {}).get("data")
    ]
    if metadata_candidates:
        assert metadata_candidates[-1]["intake"]["specialty"] == "Dermatoloji"
    else:
        overview = client.get("/api/clinical/overview", headers={"Authorization": f"Bearer {operator_token}"}).json()
        review = next(item for item in overview["shadow_reviews"] if item["conversation_id"] == data["conversation_id"])
        assert review["metadata_json"]["data"]["intake"]["specialty"] == "Dermatoloji"


def test_external_voice_processing_is_blocked_by_default(client, operator_token):
    transcribe = client.post(
        "/api/voice/transcribe",
        headers={"Authorization": f"Bearer {operator_token}"},
        files={"file": ("recording.webm", b"not-real-audio", "audio/webm")},
    )
    assert transcribe.status_code == 403
    assert "local-first" in transcribe.json()["detail"]

    synthesize = client.post(
        "/api/voice/synthesize",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={"text": "Merhaba"},
    )
    assert synthesize.status_code == 403
    assert "local-first" in synthesize.json()["detail"]
