from __future__ import annotations

from datetime import datetime, timedelta, timezone
import random

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


# ──────────────────────────────────────────────────────────────────────────────
# Customer profiles — realistic Turkish + international enterprise users
# ──────────────────────────────────────────────────────────────────────────────
CUSTOMER_PROFILES = [
    # Turkish customers
    {"full_name": "Ayşe Demir",         "email": "ayse@cognivault.com",        "locale": "tr", "dept": "Customer Operations",   "title": "Customer",           "phone": "+90 555 111 22 33"},
    {"full_name": "Mehmet Yılmaz",      "email": "mehmet@cognivault.com",      "locale": "tr", "dept": "Procurement",           "title": "Procurement Lead",   "phone": "+90 532 200 44 55"},
    {"full_name": "Fatma Şahin",        "email": "fatma@cognivault.com",       "locale": "tr", "dept": "Finance",               "title": "Finance Analyst",    "phone": "+90 541 300 66 77"},
    {"full_name": "Ali Çelik",          "email": "ali@cognivault.com",         "locale": "tr", "dept": "IT",                    "title": "IT Specialist",      "phone": "+90 505 400 88 99"},
    {"full_name": "Zeynep Arslan",      "email": "zeynep@cognivault.com",      "locale": "tr", "dept": "Legal",                 "title": "Legal Counsel",      "phone": "+90 533 500 11 22"},
    {"full_name": "Emre Kaya",          "email": "emre@cognivault.com",        "locale": "tr", "dept": "Sales",                 "title": "Sales Manager",      "phone": "+90 542 600 33 44"},
    {"full_name": "Selin Öztürk",       "email": "selin@cognivault.com",       "locale": "tr", "dept": "HR",                    "title": "HR Specialist",      "phone": "+90 506 700 55 66"},
    {"full_name": "Burak Aydın",        "email": "burak@cognivault.com",       "locale": "tr", "dept": "Engineering",           "title": "Senior Engineer",    "phone": "+90 534 800 77 88"},
    {"full_name": "Merve Doğan",        "email": "merve@cognivault.com",       "locale": "tr", "dept": "Marketing",             "title": "Marketing Lead",     "phone": "+90 543 900 99 00"},
    {"full_name": "Kerem Polat",        "email": "kerem@cognivault.com",       "locale": "tr", "dept": "Customer Success",      "title": "CS Manager",         "phone": "+90 507 111 22 33"},
    {"full_name": "Elif Güneş",         "email": "elif@cognivault.com",        "locale": "tr", "dept": "Product",               "title": "Product Manager",    "phone": "+90 535 222 44 55"},
    {"full_name": "Tolga Aksoy",        "email": "tolga@cognivault.com",       "locale": "tr", "dept": "Data",                  "title": "Data Analyst",       "phone": "+90 544 333 66 77"},
    {"full_name": "Gizem Çetin",        "email": "gizem@cognivault.com",       "locale": "tr", "dept": "Compliance",            "title": "Compliance Officer", "phone": "+90 508 444 88 99"},
    {"full_name": "Serkan Yıldız",      "email": "serkan@cognivault.com",      "locale": "tr", "dept": "Operations",            "title": "Ops Analyst",        "phone": "+90 536 555 00 11"},
    {"full_name": "Aylin Karaca",       "email": "aylin@cognivault.com",       "locale": "tr", "dept": "Logistics",             "title": "Logistics Lead",     "phone": "+90 545 666 22 33"},
    # International customers
    {"full_name": "John Carter",        "email": "john@cognivault.com",        "locale": "en", "dept": "Customer Success",      "title": "Customer",           "phone": "+44 7700 900 001"},
    {"full_name": "Sarah Mitchell",     "email": "sarah@cognivault.com",       "locale": "en", "dept": "Finance",               "title": "CFO",                "phone": "+44 7700 900 002"},
    {"full_name": "James O'Brien",      "email": "james@cognivault.com",       "locale": "en", "dept": "Engineering",           "title": "CTO",                "phone": "+44 7700 900 003"},
    {"full_name": "Lena Müller",        "email": "lena@cognivault.com",        "locale": "en", "dept": "Compliance",            "title": "GDPR Officer",       "phone": "+49 1511 234 5678"},
    {"full_name": "Marco Rossi",        "email": "marco@cognivault.com",       "locale": "en", "dept": "Sales",                 "title": "Sales Director",     "phone": "+39 333 456 7890"},
    {"full_name": "Sophie Dubois",      "email": "sophie@cognivault.com",      "locale": "en", "dept": "Legal",                 "title": "Legal Director",     "phone": "+33 6 12 34 56 78"},
    {"full_name": "Ahmet Özkan",        "email": "ahmet@cognivault.com",       "locale": "tr", "dept": "IT",                    "title": "IT Manager",         "phone": "+90 537 777 44 55"},
    {"full_name": "Derya Koç",          "email": "derya@cognivault.com",       "locale": "tr", "dept": "Procurement",           "title": "Senior Buyer",       "phone": "+90 546 888 66 77"},
    {"full_name": "Caner Şimşek",       "email": "caner@cognivault.com",       "locale": "tr", "dept": "Security",              "title": "Security Analyst",   "phone": "+90 509 999 88 99"},
    {"full_name": "Nur Aşan",           "email": "nur@cognivault.com",         "locale": "tr", "dept": "Marketing",             "title": "Brand Manager",      "phone": "+90 538 000 00 11"},
]

OPERATOR_PROFILES = [
    {"full_name": "Selin Kaya",   "email": "operator@cognivault.com",  "locale": "tr", "dept": "Operations",  "title": "Operator"},
    {"full_name": "Tuba Erdoğan", "email": "operator2@cognivault.com", "locale": "tr", "dept": "Operations",  "title": "Senior Operator"},
    {"full_name": "David Kim",    "email": "operator3@cognivault.com", "locale": "en", "dept": "Operations",  "title": "Operations Specialist"},
]

ADMIN_PROFILES = [
    {"full_name": "Mert Yıldız",     "email": "admin@cognivault.com",  "locale": "en", "dept": "Security",    "title": "Admin"},
    {"full_name": "Ece Başaran",     "email": "admin2@cognivault.com", "locale": "tr", "dept": "Engineering", "title": "Platform Engineer"},
]

# ──────────────────────────────────────────────────────────────────────────────
# Slot templates: department, day_offset, hour, location
# ──────────────────────────────────────────────────────────────────────────────
SLOT_TEMPLATES = [
    # Onboarding Desk — morning slots
    ("Onboarding Desk", 1,  9,  "Virtual Room A"),
    ("Onboarding Desk", 1,  11, "Virtual Room A"),
    ("Onboarding Desk", 2,  10, "Virtual Room A"),
    ("Onboarding Desk", 3,  9,  "Virtual Room B"),
    ("Onboarding Desk", 4,  11, "Virtual Room B"),
    ("Onboarding Desk", 5,  14, "Virtual Room A"),
    ("Onboarding Desk", 7,  9,  "Virtual Room A"),
    ("Onboarding Desk", 8,  10, "Virtual Room B"),
    ("Onboarding Desk", 10, 11, "Virtual Room A"),
    ("Onboarding Desk", 12, 9,  "Virtual Room B"),
    # Technical Support — afternoon slots
    ("Technical Support", 1,  14, "Ops Bridge"),
    ("Technical Support", 2,  10, "Ops Bridge"),
    ("Technical Support", 2,  15, "Ops Bridge"),
    ("Technical Support", 3,  13, "Remote Hub"),
    ("Technical Support", 4,  11, "Ops Bridge"),
    ("Technical Support", 5,  16, "Remote Hub"),
    ("Technical Support", 6,  9,  "Ops Bridge"),
    ("Technical Support", 8,  14, "Remote Hub"),
    ("Technical Support", 9,  10, "Ops Bridge"),
    ("Technical Support", 11, 13, "Remote Hub"),
    # Billing Operations — mid-day slots
    ("Billing Operations", 2,  13, "Finance Desk"),
    ("Billing Operations", 3,  15, "Finance Desk"),
    ("Billing Operations", 4,  10, "Finance Desk"),
    ("Billing Operations", 5,  11, "Finance Desk"),
    ("Billing Operations", 6,  14, "Finance Desk"),
    ("Billing Operations", 7,  13, "Finance Desk"),
    ("Billing Operations", 9,  15, "Finance Desk"),
    ("Billing Operations", 10, 10, "Finance Desk"),
    ("Billing Operations", 13, 11, "Finance Desk"),
    ("Billing Operations", 14, 14, "Finance Desk"),
    # Compliance Advisory — end of day
    ("Compliance Advisory", 3,  11, "Governance Hub"),
    ("Compliance Advisory", 4,  16, "Governance Hub"),
    ("Compliance Advisory", 5,  15, "Governance Hub"),
    ("Compliance Advisory", 6,  14, "Governance Hub"),
    ("Compliance Advisory", 7,  11, "Governance Hub"),
    ("Compliance Advisory", 8,  16, "Governance Hub"),
    ("Compliance Advisory", 10, 14, "Governance Hub"),
    ("Compliance Advisory", 11, 15, "Governance Hub"),
    ("Compliance Advisory", 14, 11, "Governance Hub"),
    ("Compliance Advisory", 15, 16, "Governance Hub"),
]

# ──────────────────────────────────────────────────────────────────────────────
# Sample chat histories — realistic conversations for demo purposes
# ──────────────────────────────────────────────────────────────────────────────
SAMPLE_CONVERSATIONS = [
    {
        "locale": "tr",
        "title": "Teknik destek randevusu",
        "messages": [
            ("user", "Merhaba, SAP sistemine erişemiyorum."),
            ("assistant", "Merhaba! Bunu duyduğuma üzüldüm, iş akışınızı etkiliyor olmalı. Teknik Destek ekibimiz tam bu konularda uzman. Hemen bir randevu açayım mı?"),
            ("user", "Evet lütfen."),
            ("assistant", "Harika! Telefon numaranızı paylaşır mısınız, teyit için kullanalım?"),
            ("user", "+90 532 200 44 55"),
            ("assistant", "Teşekkürler. Uygun slotlara bakıyorum..."),
        ],
    },
    {
        "locale": "tr",
        "title": "Fatura şikayeti",
        "messages": [
            ("user", "Faturamda hatalı bir ücret görüyorum."),
            ("assistant", "Anlıyorum, bu tür durumlar can sıkıcı olabiliyor. Billing Operations ekibimiz fatura anlaşmazlıklarını çözme konusunda uzmanlaşmış. Sizi onlarla buluşturayım mı?"),
            ("user", "Evet, ne zaman müsaitler?"),
            ("assistant", "Bugün ve yarın için uygun slotları listeliyorum, bir saniye..."),
        ],
    },
    {
        "locale": "en",
        "title": "Compliance advisory session",
        "messages": [
            ("user", "I need to discuss GDPR compliance requirements for our new data pipeline."),
            ("assistant", "Absolutely, that's an important topic. Our Compliance Advisory team specializes in exactly this. Shall I check available slots for you?"),
            ("user", "Yes please, preferably in the morning."),
            ("assistant", "Looking for morning slots with Compliance Advisory..."),
        ],
    },
    {
        "locale": "en",
        "title": "Onboarding assistance",
        "messages": [
            ("user", "We just signed the contract and need help getting started."),
            ("assistant", "Congratulations on getting started! Our Onboarding Desk team will walk you through everything step by step. Want me to book a session?"),
            ("user", "That would be great."),
            ("assistant", "Perfect! What's the best phone number to reach you for confirmation?"),
        ],
    },
    {
        "locale": "tr",
        "title": "Uyum danışmanlığı",
        "messages": [
            ("user", "KVK uyumu için ne yapmamız gerekiyor?"),
            ("assistant", "KVK uyumu ciddi bir konu, doğru danışmanlık almanız önemli. Compliance Advisory ekibimiz bu konuda detaylı rehberlik sağlayabilir. Randevu ayarlayalım mı?"),
            ("user", "Evet, bu hafta içinde olursa iyi olur."),
        ],
    },
]


def seed_database(db: Session) -> None:
    if db.scalars(select(Role)).first():
        seed_enterprise_demo(db)
        return

    # ── Roles ────────────────────────────────────────────────────────────────
    roles = [
        Role(name=RoleName.CUSTOMER, description="Can create and view only their own requests."),
        Role(name=RoleName.OPERATOR, description="Can manage customer workflows and appointments."),
        Role(name=RoleName.ADMIN,    description="Can view all records, users, and audit logs."),
    ]
    db.add_all(roles)
    db.commit()
    role_lookup = {role.name: role for role in db.scalars(select(Role)).all()}

    # ── Users ─────────────────────────────────────────────────────────────────
    all_users: list[User] = []

    for profile in CUSTOMER_PROFILES:
        u = User(
            full_name=profile["full_name"],
            email=profile["email"],
            hashed_password=hash_password("demo123"),
            locale=profile["locale"],
            department=profile["dept"],
            title=profile["title"],
            phone=profile.get("phone"),
            role_id=role_lookup[RoleName.CUSTOMER].id,
            is_active=True,
        )
        all_users.append(u)

    for profile in OPERATOR_PROFILES:
        u = User(
            full_name=profile["full_name"],
            email=profile["email"],
            hashed_password=hash_password("demo123"),
            locale=profile["locale"],
            department=profile["dept"],
            title=profile["title"],
            role_id=role_lookup[RoleName.OPERATOR].id,
            is_active=True,
        )
        all_users.append(u)

    for profile in ADMIN_PROFILES:
        u = User(
            full_name=profile["full_name"],
            email=profile["email"],
            hashed_password=hash_password("demo123"),
            locale=profile["locale"],
            department=profile["dept"],
            title=profile["title"],
            role_id=role_lookup[RoleName.ADMIN].id,
            is_active=True,
        )
        all_users.append(u)

    db.add_all(all_users)
    db.commit()

    user_lookup = {u.email: u for u in db.scalars(select(User)).all()}

    # ── Appointment slots ─────────────────────────────────────────────────────
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    slots: list[AppointmentSlot] = []
    for department, day_offset, hour, location in SLOT_TEMPLATES:
        start_time = (now + timedelta(days=day_offset)).replace(hour=hour, minute=0, second=0, microsecond=0)
        slots.append(AppointmentSlot(
            department=department,
            start_time=start_time,
            end_time=start_time + timedelta(minutes=45),
            location=location,
            is_booked=False,
        ))
    db.add_all(slots)
    db.commit()

    # ── Sample booked appointments ────────────────────────────────────────────
    slot_by_dept = {}
    for slot in db.scalars(select(AppointmentSlot)).all():
        slot_by_dept.setdefault(slot.department, []).append(slot)

    operator = user_lookup.get("operator@cognivault.com")
    booked_appointments = [
        {
            "user_email": "ayse@cognivault.com",
            "dept": "Onboarding Desk",
            "purpose": "Yeni entegrasyon süreci hakkında destek",
            "phone": "+90 555 111 22 33",
            "lang": "tr",
            "code": "CV-DEMO01",
        },
        {
            "user_email": "john@cognivault.com",
            "dept": "Technical Support",
            "purpose": "VPN access configuration issue",
            "phone": "+44 7700 900 001",
            "lang": "en",
            "code": "CV-DEMO02",
        },
        {
            "user_email": "fatma@cognivault.com",
            "dept": "Billing Operations",
            "purpose": "Q4 fatura anlaşmazlığı çözümü",
            "phone": "+90 541 300 66 77",
            "lang": "tr",
            "code": "CV-DEMO03",
        },
        {
            "user_email": "lena@cognivault.com",
            "dept": "Compliance Advisory",
            "purpose": "GDPR Article 30 record review",
            "phone": "+49 1511 234 5678",
            "lang": "en",
            "code": "CV-DEMO04",
        },
        {
            "user_email": "mehmet@cognivault.com",
            "dept": "Technical Support",
            "purpose": "SAP entegrasyon erişim sorunu",
            "phone": "+90 532 200 44 55",
            "lang": "tr",
            "code": "CV-DEMO05",
        },
    ]
    for appt_data in booked_appointments:
        dept_slots = slot_by_dept.get(appt_data["dept"], [])
        free_slots = [s for s in dept_slots if not s.is_booked]
        if not free_slots:
            continue
        slot = free_slots[0]
        slot.is_booked = True
        user = user_lookup.get(appt_data["user_email"])
        if user and operator:
            db.add(Appointment(
                user_id=user.id,
                slot_id=slot.id,
                department=appt_data["dept"],
                purpose=appt_data["purpose"],
                contact_phone=appt_data["phone"],
                language=appt_data["lang"],
                confirmation_code=appt_data["code"],
                created_by_user_id=operator.id,
            ))
    db.commit()

    # ── Sample chat sessions ──────────────────────────────────────────────────
    customer_emails = [p["email"] for p in CUSTOMER_PROFILES]
    for i, conv in enumerate(SAMPLE_CONVERSATIONS):
        email = customer_emails[i % len(customer_emails)]
        user = user_lookup.get(email)
        if not user:
            continue
        session = ChatSession(
            user_id=user.id,
            title=conv["title"],
            workflow_state={"language": conv["locale"], "stage": "in_progress"},
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        for sender_str, content in conv["messages"]:
            sender = MessageSender.USER if sender_str == "user" else MessageSender.ASSISTANT
            db.add(ChatMessage(
                session_id=session.id,
                sender=sender,
                content=content,
                language=conv["locale"],
                metadata_json={},
            ))
    db.commit()

    # ── Audit log entries ─────────────────────────────────────────────────────
    admin = user_lookup.get("admin@cognivault.com")
    log_action(
        db,
        user_id=admin.id if admin else None,
        action_type="system.seed",
        explanation="Demo data seeded",
        result_status=AuditResultStatus.SUCCESS,
        details={
            "users": len(all_users),
            "slots": len(slots),
            "appointments": len(booked_appointments),
            "conversations": len(SAMPLE_CONVERSATIONS),
        },
    )

    # Log a few sample failed logins for dashboard realism
    for email in ["unknown@test.com", "hacker@external.com"]:
        log_action(
            db,
            user_id=None,
            action_type="auth.login",
            explanation="Failed login attempt",
            success=False,
            result_status=AuditResultStatus.FAILURE,
            details={"email": email},
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

    dept_lookup = {d.name: d for d in db.scalars(select(Department)).all()}
    user_lookup = {u.email: u for u in db.scalars(select(User)).all()}
    operator  = user_lookup.get("operator@cognivault.com")
    operator2 = user_lookup.get("operator2@cognivault.com")
    admin     = user_lookup.get("admin@cognivault.com")

    agents = []
    if operator:
        agents.append(EnterpriseAgent(
            organization_id=organization.id,
            user_id=operator.id,
            department_id=dept_lookup["Technical Support"].id,
            display_name="Selin Kaya",
            availability_status="available",
        ))
    if operator2:
        agents.append(EnterpriseAgent(
            organization_id=organization.id,
            user_id=operator2.id,
            department_id=dept_lookup["Billing Operations"].id,
            display_name="Tuba Erdoğan",
            availability_status="available",
        ))
    if admin:
        agents.append(EnterpriseAgent(
            organization_id=organization.id,
            user_id=admin.id,
            department_id=dept_lookup["General Support"].id,
            display_name="Mert Yıldız",
            availability_status="supervisor",
        ))
    db.add_all(agents)

    routing_rules = [
        RoutingRule(
            organization_id=organization.id,
            intent="technical_issue",
            department_id=dept_lookup["Technical Support"].id,
            keywords=["internet", "çalışmıyor", "calismiyor", "erişim", "hata", "error", "sap", "entegrasyon", "vpn", "bağlanamıyorum", "sistem", "yazılım"],
            confidence_boost=78,
        ),
        RoutingRule(
            organization_id=organization.id,
            intent="billing_question",
            department_id=dept_lookup["Billing Operations"].id,
            keywords=["fatura", "ödeme", "odeme", "invoice", "billing", "ücret", "ucret", "tahsilat", "sözleşme", "sozlesme", "abonelik"],
            confidence_boost=76,
        ),
        RoutingRule(
            organization_id=organization.id,
            intent="appointment_request",
            department_id=dept_lookup["Appointment Desk"].id,
            keywords=["randevu", "appointment", "rezervasyon", "görüşme", "gorusme", "toplantı", "schedule", "buluşalım"],
            confidence_boost=82,
        ),
    ]
    db.add_all(routing_rules)
    db.commit()

    # ── Enterprise demo customers ─────────────────────────────────────────────
    demo_customers = [
        EnterpriseCustomer(
            organization_id=organization.id,
            full_name="Demo Caller",
            email="caller@example.com",
            phone="+90 555 444 33 22",
            external_ref="DEMO-CALL-001",
        ),
        EnterpriseCustomer(
            organization_id=organization.id,
            full_name="Hasan Kırmızı",
            email="hasan@enterprise-demo.com",
            phone="+90 532 111 99 88",
            external_ref="ENT-002",
        ),
        EnterpriseCustomer(
            organization_id=organization.id,
            full_name="Alice Thompson",
            email="alice@eu-corp.com",
            phone="+44 7911 123456",
            external_ref="ENT-003",
        ),
    ]
    db.add_all(demo_customers)
    db.commit()
    for dc in demo_customers:
        db.refresh(dc)

    demo_customer = demo_customers[0]
    ref_operator = operator or admin

    demo_chat = ChatSession(
        user_id=ref_operator.id,
        title="Enterprise intake - Demo Caller",
        workflow_state={"mode": "enterprise", "intent": "technical_issue"},
    )
    db.add(demo_chat)
    db.commit()
    db.refresh(demo_chat)

    demo_session = EnterpriseSession(
        organization_id=organization.id,
        customer_id=demo_customer.id,
        chat_session_id=demo_chat.id,
        department_id=dept_lookup["Technical Support"].id,
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

    db.add_all([
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
    ])
    db.add(EnterpriseTicket(
        organization_id=organization.id,
        customer_id=demo_customer.id,
        session_id=demo_session.id,
        department_id=dept_lookup["Technical Support"].id,
        intent="technical_issue",
        description="SAP entegrasyonunda erişim sorunu yaşıyorum, acil destek lazım.",
        status=EnterpriseTicketStatus.ESCALATED,
        priority="high",
        confidence=91,
        handoff_package=demo_session.handoff_package,
    ))

    # Second demo ticket — billing
    billing_chat = ChatSession(
        user_id=ref_operator.id,
        title="Enterprise intake - Alice Thompson",
        workflow_state={"mode": "enterprise", "intent": "billing_question"},
    )
    db.add(billing_chat)
    db.commit()
    db.refresh(billing_chat)

    alice = demo_customers[2]
    billing_session = EnterpriseSession(
        organization_id=organization.id,
        customer_id=alice.id,
        chat_session_id=billing_chat.id,
        department_id=dept_lookup["Billing Operations"].id,
        status=EnterpriseSessionStatus.ACTIVE,
        intent="billing_question",
        confidence=84,
        handoff_package={
            "summary": "Customer disputes invoice amount for November.",
            "intent": "billing_question",
            "suggested_department": "Billing Operations",
        },
    )
    db.add(billing_session)
    db.commit()
    db.refresh(billing_session)

    db.add_all([
        ChatMessage(
            session_id=billing_chat.id,
            sender=MessageSender.USER,
            content="My November invoice shows an incorrect amount. I was charged twice.",
            language="en",
            metadata_json={"mode": "enterprise"},
        ),
        ChatMessage(
            session_id=billing_chat.id,
            sender=MessageSender.ASSISTANT,
            content="I'm sorry to hear that. I'm routing you to our Billing Operations team who can resolve this quickly.",
            language="en",
            metadata_json={"mode": "enterprise", "intent": "billing_question"},
        ),
    ])
    db.add(EnterpriseTicket(
        organization_id=organization.id,
        customer_id=alice.id,
        session_id=billing_session.id,
        department_id=dept_lookup["Billing Operations"].id,
        intent="billing_question",
        description="Customer disputes double charge on November invoice.",
        status=EnterpriseTicketStatus.OPEN,
        priority="medium",
        confidence=84,
        handoff_package=billing_session.handoff_package,
    ))
    db.commit()
