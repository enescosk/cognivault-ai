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
    Clinic,
    ClinicBranch,
    ClinicDoctor,
    ClinicDoctorSlot,
    ClinicalAppointment,
    ClinicalAppointmentProcedure,
    ClinicalProcedureStatus,
    ClinicMembership,
    ClinicMessage,
    ClinicUserRole,
    Doctor,
    Department,
    EnterpriseAgent,
    EnterpriseCustomer,
    EnterpriseSession,
    EnterpriseSessionStatus,
    EnterpriseTicket,
    EnterpriseTicketStatus,
    KnowledgeArticle,
    MessageSender,
    Organization,
    Role,
    RoleName,
    RoutingRule,
    ShadowReview,
    User,
)
from app.services.audit_service import log_action
from app.services.clinical_service import IncomingClinicalMessage, ensure_default_clinic, ingest_clinical_message


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

CLINICIAN_PROFILES = [
    {
        "full_name": "Dr. Deniz Aksoy",
        "email": "hekim@cognivault.com",
        "locale": "tr",
        "dept": "Genel Diş Hekimliği",
        "title": "Diş Hekimi",
    },
    {"full_name": "Dr. Ece Arslan", "email": "ece.hekim@cognivault.com", "locale": "tr", "dept": "Endodonti", "title": "Endodontist"},
    {"full_name": "Dr. Burak Tan", "email": "burak.hekim@cognivault.com", "locale": "tr", "dept": "Periodontoloji", "title": "Periodontolog"},
    {"full_name": "Dr. Mina Soyer", "email": "mina.hekim@cognivault.com", "locale": "tr", "dept": "Pedodonti", "title": "Pedodontist"},
    {"full_name": "Dr. Deniz Kural", "email": "deniz.hekim@cognivault.com", "locale": "tr", "dept": "İmplantoloji", "title": "İmplantoloji Uzmanı"},
    {"full_name": "Dr. Selin Okan", "email": "selin.hekim@cognivault.com", "locale": "tr", "dept": "Restoratif Diş Tedavisi", "title": "Restoratif Diş Hekimi"},
    {"full_name": "Dr. Nehir Aydın", "email": "nehir.hekim@cognivault.com", "locale": "tr", "dept": "Dermatoloji", "title": "Dermatolog"},
    {"full_name": "Dr. Lara Demir", "email": "lara.hekim@cognivault.com", "locale": "tr", "dept": "Medikal Estetik", "title": "Medikal Estetik Hekimi"},
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


def _ensure_default_organization(db: Session) -> Organization:
    organization = db.scalars(select(Organization).order_by(Organization.id)).first()
    if organization is None:
        organization = Organization(name="Cognivault Enterprise Demo", domain="cognivault.local")
        db.add(organization)
        db.commit()
        db.refresh(organization)
    return organization


def _backfill_tenant_scopes(db: Session) -> None:
    """Wires existing clinic + staff users to the default organization.

    Idempotent: only touches rows that have a NULL organization_id, so it is safe
    to call on every startup (it is also safe to call on a fresh DB before any
    other seed step runs).
    """

    organization = _ensure_default_organization(db)

    dirty = False
    for clinic in db.scalars(select(Clinic).where(Clinic.organization_id.is_(None))).all():
        clinic.organization_id = organization.id
        db.add(clinic)
        dirty = True

    staff_roles = (RoleName.OPERATOR, RoleName.ADMIN)
    role_ids = [r.id for r in db.scalars(select(Role).where(Role.name.in_(staff_roles))).all()]
    if role_ids:
        for user in db.scalars(
            select(User).where(User.role_id.in_(role_ids), User.organization_id.is_(None))
        ).all():
            user.organization_id = organization.id
            db.add(user)
            dirty = True

    if dirty:
        db.commit()


def seed_database(db: Session) -> None:
    if db.scalars(select(Role)).first():
        ensure_demo_users(db)
        seed_enterprise_demo(db)
        seed_clinical_demo(db)
        _backfill_tenant_scopes(db)
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

    for profile in CLINICIAN_PROFILES:
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
    seed_clinical_demo(db)
    seed_clinical_doctors(db)


def ensure_demo_users(db: Session) -> None:
    role_lookup = {role.name: role for role in db.scalars(select(Role)).all()}
    profile_groups = [
        (CUSTOMER_PROFILES, RoleName.CUSTOMER),
        (OPERATOR_PROFILES, RoleName.OPERATOR),
        (CLINICIAN_PROFILES, RoleName.OPERATOR),
        (ADMIN_PROFILES, RoleName.ADMIN),
    ]

    changed = False
    for profiles, role_name in profile_groups:
        role = role_lookup.get(role_name)
        if role is None:
            role = Role(name=role_name, description=role_name.value)
            db.add(role)
            db.flush()
            role_lookup[role_name] = role
            changed = True

        for profile in profiles:
            user = db.scalars(select(User).where(User.email == profile["email"])).first()
            if user is None:
                user = User(
                    full_name=profile["full_name"],
                    email=profile["email"],
                    hashed_password=hash_password("demo123"),
                    locale=profile["locale"],
                    department=profile["dept"],
                    title=profile["title"],
                    phone=profile.get("phone"),
                    role_id=role.id,
                    is_active=True,
                )
                db.add(user)
                changed = True
                continue

            user.full_name = profile["full_name"]
            user.locale = profile["locale"]
            user.department = profile["dept"]
            user.title = profile["title"]
            user.phone = profile.get("phone")
            user.role_id = role.id
            user.hashed_password = hash_password("demo123")
            user.is_active = True
            changed = True

    if changed:
        db.commit()


def seed_enterprise_demo(db: Session) -> None:
    existing_organization = db.scalars(select(Organization)).first()
    if existing_organization:
        seed_knowledge_articles(db, existing_organization.id)
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
    seed_knowledge_articles(db, organization.id)

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


def _seed_channel_bindings(db: Session, clinic) -> None:
    """Demo kliniğin iletişim numarasını telefon+WhatsApp kanallarına bağla.

    Multi-tenant webhook yönlendirmesinin (resolve_webhook_clinic) demo'da da
    gerçek yoldan çalışmasını sağlar; idempotent.
    """
    from app.models import ClinicChannel, ClinicChannelBinding

    branding = (clinic.settings_json or {}).get("branding") or {}
    demo_number = (branding.get("contact_phone") or "+90 212 000 00 00").replace(" ", "")
    for channel in (ClinicChannel.PHONE, ClinicChannel.WHATSAPP):
        exists = db.scalars(
            select(ClinicChannelBinding).where(
                ClinicChannelBinding.channel == channel,
                ClinicChannelBinding.address == demo_number,
            )
        ).first()
        if exists is None:
            db.add(ClinicChannelBinding(clinic_id=clinic.id, channel=channel, address=demo_number))
    db.commit()


def seed_clinical_demo(db: Session) -> None:
    clinic = ensure_default_clinic(db)
    _seed_channel_bindings(db, clinic)
    users = {u.email: u for u in db.scalars(select(User)).all()}
    linked_doctors: dict[str, Doctor] = {}
    primary_doctor: Doctor | None = None
    for profile in CLINICIAN_PROFILES:
        clinician = users.get(profile["email"])
        if clinician is None:
            continue
        doctor = db.scalars(
            select(Doctor).where(Doctor.clinic_id == clinic.id, Doctor.user_id == clinician.id)
        ).first()
        if doctor is None:
            doctor = Doctor(
                clinic_id=clinic.id,
                user_id=clinician.id,
                full_name=profile["full_name"],
                specialty=profile["dept"],
                is_active=True,
            )
            db.add(doctor)
            db.flush()
        else:
            doctor.full_name = profile["full_name"]
            doctor.specialty = profile["dept"]
            doctor.is_active = True
            db.add(doctor)
        membership = db.scalars(
            select(ClinicMembership).where(
                ClinicMembership.clinic_id == clinic.id,
                ClinicMembership.user_id == clinician.id,
            )
        ).first()
        if membership is None:
            db.add(ClinicMembership(clinic_id=clinic.id, user_id=clinician.id, role=ClinicUserRole.CLINICIAN))
        else:
            membership.role = ClinicUserRole.CLINICIAN
            db.add(membership)
        linked_doctors[doctor.full_name.strip().casefold()] = doctor
        if profile["email"] == "hekim@cognivault.com":
            primary_doctor = doctor

    if primary_doctor is not None:
        for review in db.scalars(
            select(ShadowReview).where(
                ShadowReview.clinic_id == clinic.id,
                ShadowReview.assigned_doctor_id.is_(None),
            )
        ).all():
            review.assigned_doctor_id = primary_doctor.id
            db.add(review)
        procedure_templates = {
            "Endodonti": [
                ("Periapikal radyografi", "RAD-PA"),
                ("Kanal tedavisi değerlendirmesi", "ENDO-EVAL"),
            ],
            "Periodontoloji": [
                ("Periodontal muayene", "PERIO-EXAM"),
                ("Diş taşı temizliği planı", "PERIO-SCR"),
            ],
            "Pedodonti": [
                ("Çocuk ağız-diş muayenesi", "PEDO-EXAM"),
                ("Koruyucu tedavi planlaması", "PEDO-PREV"),
            ],
            "İmplantoloji": [
                ("İmplant klinik kontrolü", "IMP-CHECK"),
                ("Radyolojik değerlendirme", "RAD-PANO"),
            ],
        }
        all_appointments = db.scalars(
            select(ClinicalAppointment).where(ClinicalAppointment.clinic_id == clinic.id)
        ).all()
        for appointment in all_appointments:
            physician_name = str((appointment.metadata_json or {}).get("physician_name") or "").strip().casefold()
            matched_doctor = linked_doctors.get(physician_name) if physician_name else None
            if matched_doctor is not None:
                appointment.assigned_doctor_id = matched_doctor.id
            elif appointment.assigned_doctor_id is None:
                appointment.assigned_doctor_id = primary_doctor.id
            if not appointment.duration_minutes:
                appointment.duration_minutes = 45 if appointment.department == "Endodonti" else 30
            if appointment.starts_at and appointment.ends_at is None:
                appointment.ends_at = appointment.starts_at + timedelta(minutes=appointment.duration_minutes)
            if not appointment.visit_reason:
                appointment.visit_reason = f"{appointment.department} muayenesi ve tedavi planlaması"
            has_procedure = db.scalars(
                select(ClinicalAppointmentProcedure.id).where(
                    ClinicalAppointmentProcedure.appointment_id == appointment.id
                )
            ).first()
            if has_procedure is None:
                templates = procedure_templates.get(
                    appointment.department,
                    [("Klinik muayene", "EXAM"), ("Tedavi planlaması", "PLAN")],
                )
                for order, (name, code) in enumerate(templates):
                    db.add(
                        ClinicalAppointmentProcedure(
                            clinic_id=clinic.id,
                            appointment_id=appointment.id,
                            name=name,
                            code=code,
                            status=ClinicalProcedureStatus.PLANNED,
                            sort_order=order,
                        )
                    )
            db.add(appointment)
        db.commit()

    if db.scalars(select(ClinicMessage).where(ClinicMessage.clinic_id == clinic.id)).first():
        return

    for email, role in [
        ("admin@cognivault.com", ClinicUserRole.OWNER),
        ("operator@cognivault.com", ClinicUserRole.OPERATOR),
        ("operator2@cognivault.com", ClinicUserRole.OPERATOR),
    ]:
        user = users.get(email)
        if user is None:
            continue
        exists = db.scalars(
            select(ClinicMembership).where(ClinicMembership.clinic_id == clinic.id, ClinicMembership.user_id == user.id)
        ).first()
        if exists is None:
            db.add(ClinicMembership(clinic_id=clinic.id, user_id=user.id, role=role))
    db.commit()

    samples = [
        IncomingClinicalMessage(
            from_phone="+905551112233",
            body="Merhaba, yarin dermatoloji icin randevu var mi?",
            patient_name="Ayse Hasta",
            external_message_id="demo-wa-001",
            raw_payload={"seed": True},
        ),
        IncomingClinicalMessage(
            from_phone="+905322004455",
            body="Fiyatlariniz ve SGK geciyor mu bilgi alabilir miyim?",
            patient_name="Mehmet Hasta",
            external_message_id="demo-wa-002",
            raw_payload={"seed": True},
        ),
        IncomingClinicalMessage(
            from_phone="+905413006677",
            body="Gogsumde agri var nefes almakta zorlaniyorum ne yapmaliyim?",
            patient_name="Fatma Hasta",
            external_message_id="demo-wa-003",
            raw_payload={"seed": True},
        ),
    ]
    for item in samples:
        ingest_clinical_message(db, item, clinic=clinic)


# ──────────────────────────────────────────────────────────────────────────────
# Doctor profiles for clinical module
# ──────────────────────────────────────────────────────────────────────────────
DOCTOR_PROFILES = [
    {
        "full_name": "Dr. Elif Kaya",
        "email": "elif.kaya@cognivault-clinic.com",
        "specialty": "Diş Hekimliği",
        "title": "Dt.",
        "bio": "15 yıllık deneyimli diş hekimi. İmplant, ortodonti ve estetik diş hekimliği uzmanı.",
    },
    {
        "full_name": "Dr. Ahmet Çelik",
        "email": "ahmet.celik@cognivault-clinic.com",
        "specialty": "Dermatoloji",
        "title": "Uzm. Dr.",
        "bio": "Cilt hastalıkları, alerjik reaksiyonlar ve kozmetik dermatoloji konularında uzman.",
    },
    {
        "full_name": "Dr. Zeynep Arslan",
        "email": "zeynep.arslan@cognivault-clinic.com",
        "specialty": "Genel Pratisyen",
        "title": "Dr.",
        "bio": "Aile hekimliği ve genel muayene. Koruyucu sağlık ve kronik hastalık takibi.",
    },
    {
        "full_name": "Dr. Can Özdemir",
        "email": "can.ozdemir@cognivault-clinic.com",
        "specialty": "Psikoloji",
        "title": "Uzm. Psk.",
        "bio": "Klinik psikolog. Anksiyete, depresyon, stres yönetimi ve beslenme danışmanlığı.",
    },
]


def seed_clinical_doctors(db: Session) -> None:
    """Idempotent: create demo doctors and 7-day time slots for the demo clinic."""
    from datetime import date, time as dt_time

    clinic = ensure_default_clinic(db)

    # Get or create branch
    branch = db.scalars(
        select(ClinicBranch).where(ClinicBranch.clinic_id == clinic.id)
    ).first()

    for profile in DOCTOR_PROFILES:
        existing = db.scalars(
            select(ClinicDoctor).where(
                ClinicDoctor.clinic_id == clinic.id,
                ClinicDoctor.email == profile["email"],
            )
        ).first()
        if existing is not None:
            continue

        doctor = ClinicDoctor(
            clinic_id=clinic.id,
            branch_id=branch.id if branch else None,
            full_name=profile["full_name"],
            email=profile["email"],
            specialty=profile["specialty"],
            title=profile["title"],
            bio=profile["bio"],
        )
        db.add(doctor)
        db.flush()

        # Generate 30-min slots for 7 days (09:00-17:00, skip 12:30-13:30 lunch)
        today = date.today()
        for day_offset in range(7):
            current_date = today + timedelta(days=day_offset)
            slot_hour = 9
            slot_minute = 0
            while True:
                start = datetime.combine(
                    current_date,
                    dt_time(slot_hour, slot_minute),
                    tzinfo=timezone.utc,
                )
                end = start + timedelta(minutes=30)

                # Skip lunch break: 12:30 - 13:30
                if (slot_hour == 12 and slot_minute == 30) or (slot_hour == 13 and slot_minute == 0):
                    slot_minute += 30
                    if slot_minute >= 60:
                        slot_hour += 1
                        slot_minute = 0
                    continue

                if slot_hour >= 17:
                    break

                db.add(ClinicDoctorSlot(
                    doctor_id=doctor.id,
                    clinic_id=clinic.id,
                    start_time=start,
                    end_time=end,
                ))

                slot_minute += 30
                if slot_minute >= 60:
                    slot_hour += 1
                    slot_minute = 0

    db.commit()


def seed_knowledge_articles(db: Session, organization_id: int) -> None:
    if db.scalars(select(KnowledgeArticle).where(KnowledgeArticle.organization_id == organization_id)).first():
        return

    articles = [
        KnowledgeArticle(
            organization_id=organization_id,
            title="VPN and internet outage triage",
            content=(
                "Confirm whether the customer is on VPN or office network. Ask for error message, affected service, "
                "start time, and whether colleagues are affected. If business-critical access is blocked, mark priority high."
            ),
            tags=["technical", "vpn", "internet", "incident"],
        ),
        KnowledgeArticle(
            organization_id=organization_id,
            title="Invoice dispute playbook",
            content=(
                "Capture invoice number, billing period, contract reference, disputed amount and requested correction. "
                "Route to Billing Operations and keep the ticket open until finance confirms the adjustment."
            ),
            tags=["billing", "invoice", "payment"],
        ),
        KnowledgeArticle(
            organization_id=organization_id,
            title="Appointment and reschedule policy",
            content=(
                "Appointments require a reachable phone number and an available slot. For reschedules, release the previous "
                "slot and book the newly selected slot before sending confirmation."
            ),
            tags=["appointment", "reschedule", "scheduling"],
        ),
        KnowledgeArticle(
            organization_id=organization_id,
            title="Human handoff quality checklist",
            content=(
                "A handoff should include customer identity, intent, department, urgency, latest message, matched knowledge, "
                "confidence score and the next best action for the operator."
            ),
            tags=["handoff", "quality", "operator"],
        ),
    ]
    db.add_all(articles)
    db.commit()
