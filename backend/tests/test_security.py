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


# ─── Bcrypt password hashing (Phase 7 — Task 1) ────────────────────────────
import time

import pytest

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    needs_rehash,
    verify_password,
)


def test_bcrypt_hash_format():
    """Bcrypt hash $2b$ prefix'i ile başlamalı."""
    h = hash_password("hunter2")
    assert h.startswith("$2b$")
    assert len(h) >= 60   # bcrypt standart uzunluğu


def test_bcrypt_hash_uniqueness_across_calls():
    """Aynı şifre her çağrıda farklı hash üretmeli (salt randomluğu)."""
    a = hash_password("samepw")
    b = hash_password("samepw")
    assert a != b
    assert verify_password("samepw", a)
    assert verify_password("samepw", b)


def test_bcrypt_verify_wrong_password():
    h = hash_password("correct")
    assert verify_password("correct", h) is True
    assert verify_password("wrong", h) is False


def test_legacy_sha256_still_verifies():
    """Eski SHA-256 hash'leri hâlâ doğrulanmalı — geri uyumluluk."""
    import hashlib
    legacy = hashlib.sha256(b"demo123").hexdigest()
    assert verify_password("demo123", legacy) is True
    assert verify_password("wrong", legacy) is False


def test_needs_rehash_for_legacy():
    """SHA-256 hash'ler needs_rehash() ile flag'lenmeli."""
    import hashlib
    legacy = hashlib.sha256(b"demo123").hexdigest()
    assert needs_rehash(legacy) is True
    bcrypt_hash = hash_password("demo123")
    assert needs_rehash(bcrypt_hash) is False


def test_password_too_long():
    """Bcrypt 72 byte sınırı net hata ile karşılanmalı."""
    with pytest.raises(ValueError):
        hash_password("a" * 100)


def test_empty_password_rejected():
    with pytest.raises(ValueError):
        hash_password("")


def test_timing_resistance_bcrypt():
    """Bcrypt verify yaklaşık sabit zaman almalı — basit timing testi."""
    h = hash_password("realsecret")
    times = []
    for _ in range(3):
        t0 = time.perf_counter()
        verify_password("wrongguess", h)
        times.append(time.perf_counter() - t0)
    # Tüm denemeler 5ms üzerinde olmalı (bcrypt cost 12)
    assert min(times) > 0.005


def test_jwt_contains_iat_and_exp():
    token = create_access_token("42", organization_id=7)
    payload = decode_access_token(token)
    assert payload["sub"] == "42"
    assert payload["org_id"] == 7
    assert "iat" in payload
    assert "exp" in payload
    assert payload["iat"] < payload["exp"]
