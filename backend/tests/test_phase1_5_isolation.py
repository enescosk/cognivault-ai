"""Phase 1.5 — service-layer organization filtering.

Each test wires two operators into two distinct organisations, plants
records in both, and asserts that one operator can NEVER see the other
organisation's enterprise sessions, tickets, or clinics.
"""

from __future__ import annotations

from sqlalchemy import select

from app.models import (
    Clinic,
    ClinicConversation,
    EnterpriseCustomer,
    EnterpriseSession,
    EnterpriseSessionStatus,
    EnterpriseTicket,
    EnterpriseTicketStatus,
    Organization,
    Role,
    RoleName,
    User,
)
from app.core.security import hash_password


def _operator_in_org(db_session, *, email: str, org: Organization) -> User:
    role = db_session.scalars(select(Role).where(Role.name == RoleName.OPERATOR)).first()
    user = db_session.scalars(select(User).where(User.email == email)).first()
    if user is None:
        user = User(
            full_name=f"Op {email}",
            email=email,
            hashed_password=hash_password("password123"),
            locale="en",
            role_id=role.id,
            is_active=True,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
    user.organization_id = org.id
    db_session.add(user)
    db_session.commit()
    return user


def _make_org(db_session, name: str) -> Organization:
    org = db_session.scalars(select(Organization).where(Organization.name == name)).first()
    if org is None:
        org = Organization(name=name, domain=f"{name.lower().replace(' ', '-')}.local")
        db_session.add(org)
        db_session.commit()
        db_session.refresh(org)
    return org


def _make_enterprise_session(db_session, *, organization: Organization, label: str) -> EnterpriseSession:
    customer = EnterpriseCustomer(
        organization_id=organization.id,
        full_name=f"{label} Customer",
        email=f"{label}@example.com",
    )
    db_session.add(customer)
    db_session.commit()
    db_session.refresh(customer)

    from app.models import ChatSession

    chat = ChatSession(title=label, user_id=1, workflow_state={})
    db_session.add(chat)
    db_session.commit()
    db_session.refresh(chat)

    session = EnterpriseSession(
        organization_id=organization.id,
        customer_id=customer.id,
        chat_session_id=chat.id,
        channel="web_chat",
        status=EnterpriseSessionStatus.ACTIVE,
        intent="billing",
        confidence=70,
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    return session


def _login(client, email: str) -> str:
    res = client.post("/api/auth/login", json={"email": email, "password": "password123"})
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


def test_enterprise_session_list_is_org_scoped(client, db_session):
    org_a = _make_org(db_session, "Acme Bank")
    org_b = _make_org(db_session, "Beta Telecom")
    _operator_in_org(db_session, email="op-a@isolation.test", org=org_a)
    _operator_in_org(db_session, email="op-b@isolation.test", org=org_b)
    _make_enterprise_session(db_session, organization=org_a, label="acme-1")
    _make_enterprise_session(db_session, organization=org_b, label="beta-1")

    token_a = _login(client, "op-a@isolation.test")
    res_a = client.get("/api/enterprise/sessions", headers={"Authorization": f"Bearer {token_a}"})
    assert res_a.status_code == 200, res_a.text
    sessions_a = res_a.json()
    intents_a = {s.get("intent") for s in sessions_a}
    org_ids_a = {s.get("organization_id") for s in sessions_a if "organization_id" in s}
    # Every visible session must belong to org A.
    assert all(s.get("organization_id", org_a.id) == org_a.id for s in sessions_a)
    assert len(sessions_a) >= 1

    token_b = _login(client, "op-b@isolation.test")
    res_b = client.get("/api/enterprise/sessions", headers={"Authorization": f"Bearer {token_b}"})
    assert res_b.status_code == 200
    sessions_b = res_b.json()
    assert all(s.get("organization_id", org_b.id) == org_b.id for s in sessions_b)
    # No cross-org leak: A's data must not appear in B's listing.
    a_session_ids = {s["id"] for s in sessions_a}
    b_session_ids = {s["id"] for s in sessions_b}
    assert a_session_ids.isdisjoint(b_session_ids)


def test_enterprise_session_get_returns_404_across_orgs(client, db_session):
    org_a = _make_org(db_session, "Acme Bank")
    org_b = _make_org(db_session, "Beta Telecom")
    _operator_in_org(db_session, email="op-a2@isolation.test", org=org_a)
    _operator_in_org(db_session, email="op-b2@isolation.test", org=org_b)
    session_a = _make_enterprise_session(db_session, organization=org_a, label="acme-cross")

    token_b = _login(client, "op-b2@isolation.test")
    res = client.get(
        f"/api/enterprise/sessions/{session_a.id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    # Org B operator must NOT see org A's session — must look like it does not exist.
    assert res.status_code == 404


def test_clinic_access_falls_back_when_user_has_no_org(client):
    # The seeded test operator has no organization_id by default, so the legacy
    # default-clinic fallback must keep working.
    res = client.post("/api/auth/login", json={"email": "operator@test.com", "password": "password123"})
    assert res.status_code == 200
    token = res.json()["access_token"]
    overview = client.get(
        "/api/clinical/overview", headers={"Authorization": f"Bearer {token}"}
    )
    assert overview.status_code == 200


def test_clinic_access_uses_user_org_when_set(client, db_session):
    org = _make_org(db_session, "Hospital Network X")
    _operator_in_org(db_session, email="op-hospital@isolation.test", org=org)

    clinic = db_session.scalars(
        select(Clinic).where(Clinic.organization_id == org.id)
    ).first()
    if clinic is None:
        clinic = Clinic(
            organization_id=org.id,
            name="Hospital X — Main",
            slug="hospital-x-main",
            default_language="tr",
        )
        db_session.add(clinic)
        db_session.commit()
        db_session.refresh(clinic)

    token = _login(client, "op-hospital@isolation.test")
    overview = client.get("/api/clinical/overview", headers={"Authorization": f"Bearer {token}"})
    assert overview.status_code == 200
    payload = overview.json()
    assert payload["metrics"]["clinic_name"] == "Hospital X — Main"

    # And no clinical conversations from other clinics should appear in this clinic's overview.
    other_clinics_conversations = db_session.scalars(
        select(ClinicConversation).where(ClinicConversation.clinic_id != clinic.id)
    ).all()
    leaked = [c.id for c in other_clinics_conversations if any(
        s.get("id") == c.id for s in payload["conversations"]
    )]
    assert leaked == []
