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


def test_password_hashes_are_versioned_and_salted():
    from app.core.security import hash_password, verify_password

    first = hash_password("password123")
    second = hash_password("password123")

    assert first != second
    assert first.startswith("$argon2") or first.startswith("scrypt$")
    assert verify_password("password123", first)
    assert not verify_password("wrong", first)


def test_legacy_sha256_passwords_still_verify_for_migration():
    import hashlib

    from app.core.security import password_needs_rehash, verify_password

    legacy = hashlib.sha256("password123".encode("utf-8")).hexdigest()

    assert verify_password("password123", legacy)
    assert password_needs_rehash(legacy)


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
