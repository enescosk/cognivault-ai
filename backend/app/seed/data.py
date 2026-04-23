from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import (
    Appointment,
    AppointmentSlot,
    AuditResultStatus,
    ChatMessage,
    ChatSession,
    Department,
    EnterpriseAgent,
    EnterpriseCustomer,
    EnterpriseSession,
    EnterpriseSessionStatus,
    EnterpriseTicket,
    EnterpriseTicketStatus,
    MessageSender,
    Organization,
    Role,
    RoleName,
    RoutingRule,
    User,
)
from app.services.audit_service import log_action


def seed_database(db: Session) -> None:
    if db.scalars(select(Role)).first():
        seed_enterprise_demo(db)
        return

    roles = [
        Role(name=RoleName.CUSTOMER, description="Can create and view only their own requests."),
        Role(name=RoleName.OPERATOR, description="Can manage customer workflows and appointments."),
        Role(name=RoleName.ADMIN, description="Can view all records, users, and audit logs."),
    ]
    db.add_all(roles)
    db.commit()

    role_lookup = {role.name: role for role in db.scalars(select(Role)).all()}
    users = [
        User(
            full_name="Ayse Demir",
            email="ayse@cognivault.local",
            hashed_password=hash_password("demo123"),
            locale="tr",
            department="Customer Operations",
            title="Customer",
            role_id=role_lookup[RoleName.CUSTOMER].id,
        ),
        User(
            full_name="John Carter",
            email="john@cognivault.local",
            hashed_password=hash_password("demo123"),
            locale="en",
            department="Customer Success",
            title="Customer",
            role_id=role_lookup[RoleName.CUSTOMER].id,
        ),
        User(
            full_name="Selin Kaya",
            email="operator@cognivault.local",
            hashed_password=hash_password("demo123"),
            locale="tr",
            department="Operations",
            title="Operator",
            role_id=role_lookup[RoleName.OPERATOR].id,
        ),
        User(
            full_name="Mert Yildiz",
            email="admin@cognivault.local",
            hashed_password=hash_password("demo123"),
            locale="en",
            department="Security",
            title="Admin",
            role_id=role_lookup[RoleName.ADMIN].id,
        ),
    ]
    db.add_all(users)
    db.commit()

    user_lookup = {user.email: user for user in db.scalars(select(User)).all()}
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    slot_templates = [
        ("Onboarding Desk", 1, 9, "Virtual Room A"),
        ("Onboarding Desk", 1, 11, "Virtual Room A"),
        ("Technical Support", 1, 14, "Ops Bridge"),
        ("Technical Support", 2, 10, "Ops Bridge"),
        ("Billing Operations", 2, 13, "Finance Desk"),
        ("Billing Operations", 3, 15, "Finance Desk"),
        ("Compliance Advisory", 3, 11, "Governance Hub"),
        ("Compliance Advisory", 4, 16, "Governance Hub"),
    ]
    slots = []
    for department, day_offset, hour, location in slot_templates:
        start_time = now + timedelta(days=day_offset)
        start_time = start_time.replace(hour=hour)
        slots.append(
            AppointmentSlot(
                department=department,
                start_time=start_time,
                end_time=start_time + timedelta(minutes=45),
                location=location,
                is_booked=False,
            )
        )
    db.add_all(slots)
    db.commit()

    first_slot = db.scalars(select(AppointmentSlot).where(AppointmentSlot.department == "Onboarding Desk")).first()
    if first_slot is not None:
        first_slot.is_booked = True
        sample_appointment = Appointment(
            user_id=user_lookup["ayse@cognivault.local"].id,
            slot_id=first_slot.id,
            department=first_slot.department,
            purpose="Yeni entegrasyon süreci hakkında destek",
            contact_phone="+90 555 111 22 33",
            language="tr",
            confirmation_code="CV-DEMO01",
            created_by_user_id=user_lookup["operator@cognivault.local"].id,
        )
        db.add(sample_appointment)
        db.commit()

    session = ChatSession(
        user_id=user_lookup["ayse@cognivault.local"].id,
        title="Randevu takibi",
        workflow_state={"intent": "appointment_booking", "stage": "completed", "language": "tr"},
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    db.add_all(
        [
            ChatMessage(
                session_id=session.id,
                sender=MessageSender.USER,
                content="Teknik destek için bir randevu almak istiyorum.",
                language="tr",
                metadata_json={},
            ),
            ChatMessage(
                session_id=session.id,
                sender=MessageSender.ASSISTANT,
                content="Memnuniyetle yardımcı olurum. Uygun slotları paylaşabilirim.",
                language="tr",
                metadata_json={},
            ),
        ]
    )
    db.commit()

    log_action(
        db,
        user_id=user_lookup["admin@cognivault.local"].id,
        action_type="system.seed",
        explanation="Demo data seeded",
        result_status=AuditResultStatus.SUCCESS,
        details={"users": 4, "slots": len(slot_templates)},
    )
    seed_enterprise_demo(db)


def seed_enterprise_demo(db: Session) -> None:
    if db.scalars(select(Organization)).first():
        return

    organization = Organization(name="Cognivault Enterprise Demo", domain="cognivault.local")
    db.add(organization)
    db.commit()
    db.refresh(organization)

    departments = [
        Department(
            organization_id=organization.id,
            name="Technical Support",
            description="Internet, access, integration and technical incident handling.",
        ),
        Department(
            organization_id=organization.id,
            name="Billing Operations",
            description="Invoice, payment, contract and billing questions.",
        ),
        Department(
            organization_id=organization.id,
            name="Appointment Desk",
            description="Appointment coordination using the existing scheduling workflow.",
        ),
        Department(
            organization_id=organization.id,
            name="General Support",
            description="Fallback queue for low-confidence or mixed-intent requests.",
        ),
    ]
    db.add_all(departments)
    db.commit()

    department_lookup = {item.name: item for item in db.scalars(select(Department)).all()}
    admin = db.scalars(select(User).where(User.email == "admin@cognivault.local")).first()
    operator = db.scalars(select(User).where(User.email == "operator@cognivault.local")).first()
    if operator:
        db.add(
            EnterpriseAgent(
                organization_id=organization.id,
                user_id=operator.id,
                department_id=department_lookup["Technical Support"].id,
                display_name="Selin Kaya",
                availability_status="available",
            )
        )
    if admin:
        db.add(
            EnterpriseAgent(
                organization_id=organization.id,
                user_id=admin.id,
                department_id=department_lookup["General Support"].id,
                display_name="Mert Yildiz",
                availability_status="supervisor",
            )
        )

    routing_rules = [
        RoutingRule(
            organization_id=organization.id,
            intent="technical_issue",
            department_id=department_lookup["Technical Support"].id,
            keywords=["internet", "çalışmıyor", "calismiyor", "erişim", "hata", "error", "sap", "entegrasyon", "vpn"],
            confidence_boost=78,
        ),
        RoutingRule(
            organization_id=organization.id,
            intent="billing_question",
            department_id=department_lookup["Billing Operations"].id,
            keywords=["fatura", "ödeme", "odeme", "invoice", "billing", "ücret", "ucret", "tahsilat"],
            confidence_boost=76,
        ),
        RoutingRule(
            organization_id=organization.id,
            intent="appointment_request",
            department_id=department_lookup["Appointment Desk"].id,
            keywords=["randevu", "appointment", "rezervasyon", "görüşme", "gorusme", "toplantı", "schedule"],
            confidence_boost=82,
        ),
    ]
    db.add_all(routing_rules)
    db.commit()

    demo_customer = EnterpriseCustomer(
        organization_id=organization.id,
        full_name="Demo Caller",
        email="caller@example.com",
        phone="+90 555 444 33 22",
        external_ref="DEMO-CALL-001",
    )
    demo_chat = ChatSession(
        user_id=operator.id if operator else admin.id,
        title="Enterprise intake - Demo Caller",
        workflow_state={"mode": "enterprise", "intent": "technical_issue"},
    )
    db.add(demo_customer)
    db.add(demo_chat)
    db.commit()
    db.refresh(demo_customer)
    db.refresh(demo_chat)

    demo_session = EnterpriseSession(
        organization_id=organization.id,
        customer_id=demo_customer.id,
        chat_session_id=demo_chat.id,
        department_id=department_lookup["Technical Support"].id,
        status=EnterpriseSessionStatus.NEEDS_HUMAN,
        intent="technical_issue",
        confidence=91,
        handoff_package={
            "summary": "Customer reports SAP integration access problem.",
            "intent": "technical_issue",
            "suggested_department": "Technical Support",
            "last_messages": [],
        },
    )
    db.add(demo_session)
    db.commit()
    db.refresh(demo_session)

    db.add_all(
        [
            ChatMessage(
                session_id=demo_chat.id,
                sender=MessageSender.USER,
                content="SAP entegrasyonunda erişim sorunu yaşıyorum, acil destek lazım.",
                language="tr",
                metadata_json={"mode": "enterprise"},
            ),
            ChatMessage(
                session_id=demo_chat.id,
                sender=MessageSender.ASSISTANT,
                content="Talep Technical Support ekibine eskale edildi. Handoff paketi hazırlandı.",
                language="tr",
                metadata_json={"mode": "enterprise", "intent": "technical_issue", "action": "escalate"},
            ),
        ]
    )
    db.add(
        EnterpriseTicket(
            organization_id=organization.id,
            customer_id=demo_customer.id,
            session_id=demo_session.id,
            department_id=department_lookup["Technical Support"].id,
            intent="technical_issue",
            description="SAP entegrasyonunda erişim sorunu yaşıyorum, acil destek lazım.",
            status=EnterpriseTicketStatus.ESCALATED,
            priority="high",
            confidence=91,
            handoff_package=demo_session.handoff_package,
        )
    )
    db.commit()
