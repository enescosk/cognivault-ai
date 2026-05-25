from app.core.config import Settings


def test_default_jwt_secret_is_flagged_weak():
    settings = Settings(jwt_secret="change-me-in-production", environment="development")
    assert settings.has_weak_jwt_secret is True
    assert settings.is_production is False


def test_short_jwt_secret_is_flagged_weak():
    settings = Settings(jwt_secret="abc123", environment="development")
    assert settings.has_weak_jwt_secret is True


def test_strong_jwt_secret_passes():
    settings = Settings(jwt_secret="a" * 64, environment="production")
    assert settings.has_weak_jwt_secret is False
    assert settings.is_production is True


def test_environment_is_normalized():
    assert Settings(environment="  PRODUCTION  ").is_production is True
    assert Settings(environment="staging").is_production is True
    assert Settings(environment="dev").is_production is False


def test_request_id_header_is_set(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert "x-request-id" in {key.lower() for key in res.headers.keys()}


def test_request_id_header_is_preserved_when_supplied(client):
    res = client.get("/health", headers={"X-Request-ID": "fixed-id-123"})
    assert res.headers.get("X-Request-ID") == "fixed-id-123"


def test_agents_list_requires_operator(client, customer_token, operator_token):
    forbidden = client.get(
        "/api/agents",
        headers={"Authorization": f"Bearer {customer_token}"},
    )
    assert forbidden.status_code == 403

    allowed = client.get(
        "/api/agents",
        headers={"Authorization": f"Bearer {operator_token}"},
    )
    assert allowed.status_code == 200
    body = allowed.json()
    agent_types = {item["agent_type"] for item in body}
    assert {"appointment", "support", "form", "routing", "corporate_assistant"} <= agent_types


def test_agent_dispatch_emergency_routes_to_human(client, operator_token):
    res = client.post(
        "/api/agents/dispatch",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={
            "agent_type": "routing",
            "message": "Gogus agrim var ve nefes alamiyorum, acil yardim lazim.",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["requires_human"] is True
    assert body["risk"] == "high"
    assert body["intent"] == "emergency_escalation"


def test_agent_dispatch_appointment_intent(client, operator_token):
    res = client.post(
        "/api/agents/dispatch",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={
            "agent_type": "appointment",
            "message": "Yarin icin bir randevu almak istiyorum.",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["intent"] == "appointment_request"
    assert body["action"] == "create_appointment_draft"


def test_agent_dispatch_form_reports_missing_fields(client, operator_token):
    res = client.post(
        "/api/agents/dispatch",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={
            "agent_type": "form",
            "answers": {"name": "Ayse"},
            "required_fields": ["name", "phone", "complaint"],
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["action"] == "ask_next_question"
    assert set(body["payload"]["missing_fields"]) == {"phone", "complaint"}
