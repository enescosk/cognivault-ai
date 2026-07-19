"""Outbox operator/admin API yüzeyi."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.security import hash_password
from app.models import Organization, OutboxEvent, OutboxEventStatus, Role, RoleName, User


def _ensure_org(db_session, name: str) -> Organization:
    org = db_session.scalars(select(Organization).where(Organization.name == name)).first()
    if org is None:
        org = Organization(name=name, domain=f"{name.lower().replace(' ', '-')}.local")
        db_session.add(org)
        db_session.commit()
        db_session.refresh(org)
    return org


def _operator_in_org(db_session, email: str, org: Organization) -> User:
    role = db_session.scalars(select(Role).where(Role.name == RoleName.OPERATOR)).first()
    user = db_session.scalars(select(User).where(User.email == email)).first()
    if user is None:
        user = User(
            full_name=f"Op {email}",
            email=email,
            hashed_password=hash_password("password123"),
            locale="tr",
            role_id=role.id,
            is_active=True,
            organization_id=org.id,
        )
    else:
        user.organization_id = org.id
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _login(client, email: str) -> str:
    res = client.post("/api/auth/login", json={"email": email, "password": "password123"})
    assert res.status_code == 200
    return res.json()["access_token"]


def _add_event(
    db_session,
    *,
    event_type: str,
    status: OutboxEventStatus,
    organization_id: int | None,
    last_error: str | None = None,
    next_retry_at=None,
) -> OutboxEvent:
    event = OutboxEvent(
        event_type=event_type,
        payload_json={"body": event_type},
        status=status,
        organization_id=organization_id,
        attempts=1 if status == OutboxEventStatus.DEAD_LETTER else 0,
        max_attempts=3,
        last_error=last_error,
        next_retry_at=next_retry_at,
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)
    return event


def test_outbox_summary_is_org_scoped_and_includes_legacy_rows(client, db_session):
    org_a = _ensure_org(db_session, "Outbox Org A")
    org_b = _ensure_org(db_session, "Outbox Org B")
    _operator_in_org(db_session, "op-outbox-a@test.local", org_a)
    token_a = _login(client, "op-outbox-a@test.local")

    now = datetime.now(timezone.utc)
    _add_event(
        db_session,
        event_type="whatsapp.send",
        status=OutboxEventStatus.PENDING,
        organization_id=org_a.id,
        next_retry_at=now - timedelta(seconds=1),
    )
    dead = _add_event(
        db_session,
        event_type="email.send",
        status=OutboxEventStatus.DEAD_LETTER,
        organization_id=org_a.id,
        last_error="smtp auth failed",
    )
    _add_event(
        db_session,
        event_type="legacy.send",
        status=OutboxEventStatus.DISPATCHED,
        organization_id=None,
    )
    _add_event(
        db_session,
        event_type="whatsapp.send",
        status=OutboxEventStatus.DEAD_LETTER,
        organization_id=org_b.id,
        last_error="must not leak",
    )

    res = client.get("/api/agents/outbox/summary", headers={"Authorization": f"Bearer {token_a}"})

    assert res.status_code == 200, res.text
    data = res.json()
    assert data["total"] == 3
    assert data["by_status"]["pending"] == 1
    assert data["by_status"]["dispatched"] == 1
    assert data["by_status"]["dead_letter"] == 1
    assert data["pending_ready"] == 1
    assert data["latest_dead_letter_id"] == dead.id
    assert data["latest_dead_letter_error"] == "smtp auth failed"


def test_outbox_events_endpoint_filters_status_and_type(client, db_session):
    org = _ensure_org(db_session, "Outbox Filter Org")
    _operator_in_org(db_session, "op-outbox-filter@test.local", org)
    token = _login(client, "op-outbox-filter@test.local")

    kept = _add_event(
        db_session,
        event_type="whatsapp.send",
        status=OutboxEventStatus.DEAD_LETTER,
        organization_id=org.id,
        last_error="provider timeout",
    )
    _add_event(
        db_session,
        event_type="email.send",
        status=OutboxEventStatus.DEAD_LETTER,
        organization_id=org.id,
        last_error="smtp timeout",
    )
    _add_event(
        db_session,
        event_type="whatsapp.send",
        status=OutboxEventStatus.PENDING,
        organization_id=org.id,
    )

    res = client.get(
        "/api/agents/outbox/events?status=dead_letter&event_type=whatsapp.send",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert res.status_code == 200, res.text
    rows = res.json()
    assert [row["id"] for row in rows] == [kept.id]
    assert rows[0]["status"] == "dead_letter"
    assert rows[0]["last_error"] == "provider timeout"


def test_outbox_api_requires_operator(client, customer_token):
    summary = client.get("/api/agents/outbox/summary", headers={"Authorization": f"Bearer {customer_token}"})
    events = client.get("/api/agents/outbox/events", headers={"Authorization": f"Bearer {customer_token}"})

    assert summary.status_code == 403
    assert events.status_code == 403
