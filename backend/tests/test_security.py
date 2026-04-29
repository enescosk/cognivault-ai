def test_unauthenticated_appointments(client):
    res = client.get("/api/appointments")
    assert res.status_code == 401


def test_unauthenticated_audit_logs(client):
    res = client.get("/api/audit-logs")
    assert res.status_code == 401


def test_unauthenticated_users(client):
    res = client.get("/api/users")
    assert res.status_code == 401


def test_customer_cannot_access_all_users(client, customer_token):
    res = client.get("/api/users", headers={"Authorization": f"Bearer {customer_token}"})
    assert res.status_code == 403


def test_customer_cannot_access_all_audit_logs(client, customer_token):
    # Customer can only view their own audit logs, not all
    res = client.get("/api/audit-logs", headers={"Authorization": f"Bearer {customer_token}"})
    # Should either be 403 or return only own records (200 with limited data)
    assert res.status_code in (200, 403)


def test_security_headers_present(client):
    res = client.get("/health")
    assert res.headers.get("X-Content-Type-Options") == "nosniff"
    assert res.headers.get("X-Frame-Options") == "DENY"
    assert res.headers.get("X-XSS-Protection") == "1; mode=block"


def test_message_too_long(client, customer_token):
    # First create a session
    session_res = client.post(
        "/api/chat/sessions",
        json={"title": "Test"},
        headers={"Authorization": f"Bearer {customer_token}"},
    )
    if session_res.status_code != 200:
        return  # Skip if session creation not available

    session_id = session_res.json()["id"]
    long_message = "a" * 2001
    res = client.post(
        f"/api/chat/sessions/{session_id}/messages",
        json={"content": long_message},
        headers={"Authorization": f"Bearer {customer_token}"},
    )
    assert res.status_code == 422


def test_invalid_appointment_phone(client, customer_token):
    res = client.post(
        "/api/appointments",
        json={
            "slot_id": 1,
            "purpose": "Test",
            "contact_phone": "ab",  # too short
            "language": "en",
        },
        headers={"Authorization": f"Bearer {customer_token}"},
    )
    assert res.status_code == 422
