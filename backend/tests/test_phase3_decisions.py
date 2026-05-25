"""Phase 3 — agent decision log persistence + tenant-scoped queries."""

from __future__ import annotations

from sqlalchemy import select

from app.models import AgentDecisionLog, Organization, Role, RoleName, User
from app.core.security import hash_password


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


def _login(client, email: str) -> str:
    res = client.post("/api/auth/login", json={"email": email, "password": "password123"})
    assert res.status_code == 200
    return res.json()["access_token"]


def test_inbound_message_records_agent_decision(client, db_session, operator_token):
    before = db_session.scalar(select(__import__("sqlalchemy").func.count(AgentDecisionLog.id))) or 0

    res = client.post(
        "/api/clinical/simulate-whatsapp",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={
            "from_phone": "+90 555 123 45 67",
            "patient_name": "Karar Hasta",
            "body": "Cuma randevu alabilir miyim?",
        },
    )
    assert res.status_code == 200

    after = db_session.scalar(select(__import__("sqlalchemy").func.count(AgentDecisionLog.id))) or 0
    assert after > before

    latest = db_session.scalars(
        select(AgentDecisionLog).order_by(AgentDecisionLog.id.desc())
    ).first()
    assert latest is not None
    assert latest.agent_type in {"support", "routing"}
    assert latest.clinic_id is not None
    assert latest.conversation_id is not None


def test_emergency_inbound_records_high_risk_routing_decision(client, db_session, operator_token):
    res = client.post(
        "/api/clinical/simulate-whatsapp",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={
            "from_phone": "+90 555 222 33 44",
            "body": "Gogsumde agri var nefes alamiyorum acil yardim.",
        },
    )
    assert res.status_code == 200

    latest_routing = db_session.scalars(
        select(AgentDecisionLog)
        .where(AgentDecisionLog.agent_type == "routing", AgentDecisionLog.requires_human.is_(True))
        .order_by(AgentDecisionLog.id.desc())
    ).first()
    assert latest_routing is not None
    assert latest_routing.risk == "high"
    assert latest_routing.action == "shadow_review"


def test_pre_intake_update_records_form_decision(client, db_session, operator_token):
    seed = client.post(
        "/api/clinical/simulate-whatsapp",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={"from_phone": "+90 555 333 44 55", "body": "Sade randevu sorusu."},
    )
    patient_id = seed.json()["patient_id"]

    create = client.post(
        "/api/clinical/pre-intakes",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={"patient_id": patient_id, "answers": {}},
    )
    intake_id = create.json()["id"]

    update = client.patch(
        f"/api/clinical/pre-intakes/{intake_id}",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={"answers": {"chief_complaint": "ates"}, "is_complete": True},
    )
    assert update.status_code == 200

    latest_form = db_session.scalars(
        select(AgentDecisionLog)
        .where(AgentDecisionLog.agent_type == "form")
        .order_by(AgentDecisionLog.id.desc())
    ).first()
    assert latest_form is not None
    assert latest_form.intent == "pre_intake_progress"
    assert latest_form.action == "persist_pre_intake"
    assert latest_form.payload_json["pre_intake_id"] == intake_id


def test_decision_log_endpoint_is_org_scoped(client, db_session):
    org_a = _ensure_org(db_session, "Decision Org A")
    org_b = _ensure_org(db_session, "Decision Org B")
    _operator_in_org(db_session, "op-dec-a@isolation.test", org_a)
    _operator_in_org(db_session, "op-dec-b@isolation.test", org_b)

    # Plant a decision row in each organisation.
    for org in (org_a, org_b):
        db_session.add(
            AgentDecisionLog(
                agent_type="support",
                intent="test",
                confidence=0.9,
                risk="low",
                requires_human=False,
                organization_id=org.id,
                payload_json={"label": org.name},
            )
        )
    db_session.commit()

    token_a = _login(client, "op-dec-a@isolation.test")
    res_a = client.get("/api/agents/decisions", headers={"Authorization": f"Bearer {token_a}"})
    assert res_a.status_code == 200
    rows_a = res_a.json()
    # Org A operator must NOT see Org B's row.
    assert all(r["organization_id"] == org_a.id for r in rows_a if r.get("organization_id") is not None)
    org_b_labels = [r for r in rows_a if r.get("organization_id") == org_b.id]
    assert org_b_labels == []


def test_decision_log_detail_returns_404_across_orgs(client, db_session):
    org_a = _ensure_org(db_session, "Detail Org A")
    org_b = _ensure_org(db_session, "Detail Org B")
    _operator_in_org(db_session, "op-detail-a@isolation.test", org_a)
    _operator_in_org(db_session, "op-detail-b@isolation.test", org_b)

    row = AgentDecisionLog(
        agent_type="support",
        intent="leak_probe",
        confidence=0.5,
        risk="medium",
        requires_human=False,
        organization_id=org_a.id,
        payload_json={},
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)

    token_b = _login(client, "op-detail-b@isolation.test")
    res = client.get(
        f"/api/agents/decisions/{row.id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert res.status_code == 404


def test_decision_log_endpoint_requires_operator(client, customer_token):
    res = client.get("/api/agents/decisions", headers={"Authorization": f"Bearer {customer_token}"})
    assert res.status_code == 403
