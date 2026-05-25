"""Phase 1 / Phase 2 hardening tests: tenant scoping, JWT org claim,
webhook signature validation, inbound idempotency.
"""

from __future__ import annotations

import base64
import hashlib
import hmac

import jwt
from sqlalchemy import select

from app.core.config import get_settings
from app.models import AuditLog, InboundEvent, Organization, User


def _ensure_test_organization(db_session) -> Organization:
    org = db_session.scalars(select(Organization).where(Organization.name == "Test Org")).first()
    if org is None:
        org = Organization(name="Test Org", domain="test.local")
        db_session.add(org)
        db_session.commit()
        db_session.refresh(org)
    return org


def _wire_operator_to_org(db_session, organization_id: int, email: str = "operator@test.com") -> None:
    operator = db_session.scalars(select(User).where(User.email == email)).first()
    assert operator is not None
    operator.organization_id = organization_id
    db_session.add(operator)
    db_session.commit()


def test_user_can_be_linked_to_organization(db_session):
    org = _ensure_test_organization(db_session)
    _wire_operator_to_org(db_session, org.id)
    operator = db_session.scalars(select(User).where(User.email == "operator@test.com")).first()
    assert operator.organization_id == org.id


def test_jwt_contains_org_id_claim_when_user_has_org(client, db_session):
    org = _ensure_test_organization(db_session)
    _wire_operator_to_org(db_session, org.id)

    res = client.post("/api/auth/login", json={"email": "operator@test.com", "password": "password123"})
    assert res.status_code == 200
    token = res.json()["access_token"]

    settings = get_settings()
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    assert payload["org_id"] == org.id


def test_jwt_omits_org_claim_when_user_has_no_org(client):
    # The seeded customer in conftest has no organization_id by default.
    res = client.post("/api/auth/login", json={"email": "customer@test.com", "password": "password123"})
    assert res.status_code == 200
    token = res.json()["access_token"]
    settings = get_settings()
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    assert "org_id" not in payload


def test_webhook_idempotency_skips_duplicate(client, db_session):
    payload = {
        "From": "whatsapp:+905551112222",
        "Body": "Sade bir randevu sorusu.",
        "ProfileName": "Idem Hasta",
        "MessageSid": "SM_IDEM_001",
    }
    res1 = client.post(
        "/api/webhooks/whatsapp",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert res1.status_code == 200, res1.text
    first = res1.json()
    first_message_id = first["message_id"]

    res2 = client.post(
        "/api/webhooks/whatsapp",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert res2.status_code == 200, res2.text
    second = res2.json()
    assert second["action"] == "duplicate_ignored"
    assert second["message_id"] == first_message_id

    events = db_session.scalars(
        select(InboundEvent).where(InboundEvent.external_id == "SM_IDEM_001")
    ).all()
    assert len(events) == 1


def test_two_distinct_external_ids_both_persist(client):
    res1 = client.post(
        "/api/webhooks/whatsapp",
        data={"From": "whatsapp:+905557778800", "Body": "Selam.", "MessageSid": "SM_UNIQUE_A"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    res2 = client.post(
        "/api/webhooks/whatsapp",
        data={"From": "whatsapp:+905557778800", "Body": "Tekrar.", "MessageSid": "SM_UNIQUE_B"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert res1.status_code == 200
    assert res2.status_code == 200
    assert res1.json()["message_id"] != res2.json()["message_id"]


def test_twilio_signature_rejected_when_required(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "clinical_webhook_signature_required", True)
    monkeypatch.setattr(settings, "twilio_auth_token", "test-token")

    res = client.post(
        "/api/webhooks/whatsapp",
        data={
            "From": "whatsapp:+905552223344",
            "Body": "Imzasiz istek.",
            "MessageSid": "SM_SIG_REJECT_001",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert res.status_code == 401


def test_twilio_signature_accepted_when_valid(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "clinical_webhook_signature_required", True)
    monkeypatch.setattr(settings, "twilio_auth_token", "test-token")
    monkeypatch.setattr(settings, "clinical_webhook_base_url", "http://testserver")

    form = {
        "From": "whatsapp:+905552225566",
        "Body": "Imzali istek.",
        "MessageSid": "SM_SIG_ACCEPT_001",
    }
    canonical = "http://testserver/api/webhooks/whatsapp" + "".join(
        f"{k}{v}" for k, v in sorted(form.items())
    )
    digest = hmac.new(b"test-token", canonical.encode("utf-8"), hashlib.sha1).digest()
    signature = base64.b64encode(digest).decode("ascii")

    res = client.post(
        "/api/webhooks/whatsapp",
        data=form,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Twilio-Signature": signature,
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["ok"] is True


def test_meta_signature_required_when_flag_enabled(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "clinical_webhook_signature_required", True)
    monkeypatch.setattr(settings, "meta_app_secret", "meta-secret")

    res = client.post(
        "/api/webhooks/whatsapp",
        json={"entry": []},
    )
    assert res.status_code == 401


def test_meta_signature_accepted_when_valid(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "clinical_webhook_signature_required", True)
    monkeypatch.setattr(settings, "meta_app_secret", "meta-secret")

    body = b'{"entry":[]}'
    digest = hmac.new(b"meta-secret", body, hashlib.sha256).hexdigest()
    res = client.post(
        "/api/webhooks/whatsapp",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": f"sha256={digest}",
        },
    )
    assert res.status_code == 200, res.text


def test_audit_log_records_organization_id_for_staff(client, db_session):
    org = _ensure_test_organization(db_session)
    _wire_operator_to_org(db_session, org.id)

    res = client.post(
        "/api/auth/login",
        json={"email": "operator@test.com", "password": "password123"},
    )
    assert res.status_code == 200

    latest = db_session.scalars(
        select(AuditLog).where(AuditLog.action_type == "auth.login").order_by(AuditLog.id.desc())
    ).first()
    assert latest is not None
    assert latest.organization_id == org.id
