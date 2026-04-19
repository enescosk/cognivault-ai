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
    MessageSender,
    Role,
    RoleName,
    User,
)
from app.services.audit_service import log_action


def seed_database(db: Session) -> None:
    if db.scalars(select(Role)).first():
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
