"""Tests for chat session and message endpoints."""


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_create_session(client, customer_token):
    res = client.post("/api/chat/sessions", json={"title": "Test session"}, headers=_auth(customer_token))
    assert res.status_code == 200
    data = res.json()
    assert data["title"] == "Test session"
    assert data["status"] == "active"
    assert data["messages"] == []


def test_list_sessions_empty_for_new_user(client, customer_token):
    # customer2 has no sessions yet
    res = client.post("/api/auth/login", json={"email": "customer2@test.com", "password": "password123"})
    token = res.json()["access_token"]
    res = client.get("/api/chat/sessions", headers=_auth(token))
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_get_session(client, customer_token):
    create = client.post("/api/chat/sessions", json={"title": "Fetch me"}, headers=_auth(customer_token))
    session_id = create.json()["id"]
    res = client.get(f"/api/chat/sessions/{session_id}", headers=_auth(customer_token))
    assert res.status_code == 200
    assert res.json()["id"] == session_id


def test_get_session_unauthorized(client, customer_token):
    # customer2 cannot read customer's session
    create = client.post("/api/chat/sessions", json={"title": "Private"}, headers=_auth(customer_token))
    session_id = create.json()["id"]
    res2 = client.post("/api/auth/login", json={"email": "customer2@test.com", "password": "password123"})
    token2 = res2.json()["access_token"]
    res = client.get(f"/api/chat/sessions/{session_id}", headers=_auth(token2))
    assert res.status_code in (403, 404)


def test_create_session_requires_auth(client):
    res = client.post("/api/chat/sessions", json={"title": "No auth"})
    assert res.status_code == 401


def test_list_sessions_requires_auth(client):
    res = client.get("/api/chat/sessions")
    assert res.status_code == 401


def test_customer_medical_request_stays_in_enterprise_scope(client, customer_token, monkeypatch):
    from app.agent import orchestrator

    monkeypatch.setattr(orchestrator, "openai_enabled", lambda: False)
    monkeypatch.setattr(orchestrator, "anthropic_enabled", lambda: False)

    create = client.post("/api/chat/sessions", json={"title": "Boundary test"}, headers=_auth(customer_token))
    session_id = create.json()["id"]

    res = client.post(
        f"/api/chat/sessions/{session_id}/messages",
        json={"content": "Merhaba, diş ağrısı çekiyorum ve randevu almak istiyorum."},
        headers=_auth(customer_token),
    )

    assert res.status_code == 200
    reply = res.json()["assistant_reply"]
    assert reply["outcome"] == "unsupported_domain"
    assert "kurumsal destek randevuları" in reply["message"]
    assert "Garanti" not in reply["message"]
    assert "public kaynak" not in reply["message"]


def test_customer_chat_does_not_run_external_outreach(client, customer_token, monkeypatch):
    from app.agent import orchestrator

    monkeypatch.setattr(orchestrator, "openai_enabled", lambda: False)
    monkeypatch.setattr(orchestrator, "anthropic_enabled", lambda: False)

    create = client.post("/api/chat/sessions", json={"title": "Outreach boundary"}, headers=_auth(customer_token))
    session_id = create.json()["id"]

    res = client.post(
        f"/api/chat/sessions/{session_id}/messages",
        json={"content": "Garanti BBVA müşteri hizmetlerini ara."},
        headers=_auth(customer_token),
    )

    assert res.status_code == 200
    reply = res.json()["assistant_reply"]
    assert reply["outcome"] != "external_contact_prepared"
    assert not (reply.get("metadata_json") or {}).get("intelligence_activity")
    assert "public kaynak" not in reply["message"]
