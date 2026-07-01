"""İP-6.2 — <1 gün klinik onboarding: tek komut tenant provizyonu.

`docs/onboarding/IP-6.3-one-day-onboarding-playbook.md`'deki klinik bilgi
toplama formunu makine-okur `ClinicIntake` kontratına çevirir ve tek çağrıda
idempotent olarak provizyon eder: klinik + şube + hekim + hizmet + personel
(rol/üyelik) + versiyonlu KVKK aydınlatma metni.

İki yumuşatılamaz kural:
- **İdempotenlik** — aynı intake ikinci kez koşarsa hiçbir kayıt çiftlenmez;
  değişen alanlar günceller, değişmeyen akış no-op'tur.
- **Kiracı izolasyonu** — bir kliniğin provizyonu başka kliniğin verisine
  dokunmaz; kapı testi iki klinikle bunu doğrular.

Rapor kapıları playbook'un 10 senaryoluk kabul testinin fonksiyon seviyesinde
koşulabilir kısmını da içerir (acil yükseltme, kimlik maskeleme, çekimserlik,
KVKK versiyonu). Gerçek <1 gün doğrulaması pilot klinikte kronometreli
kurulum gerektirir — bu modül onun masa-başı otomasyon ayağıdır.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import time

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.clinical.normalizer import triage
from app.clinical.ontology import SPECIALTY_BY_CODE, UrgencyLevel
from app.clinical.selective import decide
from app.core.security import hash_password
from app.db.base import Base
from app.models.entities import (
    Clinic,
    ClinicBranch,
    ClinicMembership,
    ClinicService,
    ClinicUserRole,
    Doctor,
    KVKKDisclosureVersion,
    Role,
    RoleName,
    User,
)
from app.services.clinical_compliance_service import mask_identifiers


ARTIFACT_PATH = Path(__file__).resolve().parent / "data" / "onboarding_provision.json"
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SHADOW_SAFETY_FLOOR = 0.75  # İP-4.3 ile aynı taban: shadow eşiği bunun altına inemez.
TIME_BUDGET_SECONDS = 6 * 3600  # Playbook hedefi: 6 saat aktif kurulum.
MIN_PASSWORD_LENGTH = 8

_STAFF_ROLE_TO_MEMBERSHIP = {
    "owner": ClinicUserRole.OWNER,
    "operator": ClinicUserRole.OPERATOR,
    "clinician": ClinicUserRole.CLINICIAN,
}
_STAFF_ROLE_TO_USER_ROLE = {
    "owner": RoleName.ADMIN,
    "operator": RoleName.OPERATOR,
    "clinician": RoleName.OPERATOR,
}


# ── Intake kontratı ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class IntakeBranch:
    name: str
    address: str
    phone: str
    working_hours: dict  # {"mon": "09:00-18:00", ...}


@dataclass(frozen=True)
class IntakeDoctor:
    full_name: str
    specialty_code: str  # app.clinical.ontology kodu — tek doğru kaynak.
    is_active: bool = True


@dataclass(frozen=True)
class IntakeService:
    name: str
    description: str = ""


@dataclass(frozen=True)
class IntakeStaff:
    full_name: str
    email: str
    role: str  # owner | operator | clinician
    initial_password: str


@dataclass(frozen=True)
class ClinicIntake:
    name: str
    slug: str
    kvkk_version: str
    kvkk_text: str
    branches: tuple[IntakeBranch, ...]
    doctors: tuple[IntakeDoctor, ...]
    services: tuple[IntakeService, ...]
    staff: tuple[IntakeStaff, ...]
    default_language: str = "tr"
    timezone: str = "Europe/Istanbul"
    ai_auto_reply_threshold: float = 0.9
    shadow_review_threshold: float = 0.75


DEMO_INTAKE = ClinicIntake(
    name="Demo Diş Kliniği",
    slug="demo-dis-klinigi",
    kvkk_version="v1.0-pilot",
    kvkk_text=(
        "KVKK aydınlatma metni (pilot taslak): Kişisel verileriniz randevu ve "
        "iletişim amacıyla yerel sistemde işlenir; yurt dışına aktarılmaz. "
        "Nihai metin klinik avukatının onayıyla yayınlanır."
    ),
    branches=(
        IntakeBranch(
            name="Merkez Şube",
            address="Bağdat Cad. No:1, Kadıköy/İstanbul",
            phone="+90 216 000 00 00",
            working_hours={
                "mon": "09:00-18:00",
                "tue": "09:00-18:00",
                "wed": "09:00-18:00",
                "thu": "09:00-18:00",
                "fri": "09:00-18:00",
                "sat": "10:00-14:00",
            },
        ),
    ),
    doctors=(
        IntakeDoctor(full_name="Dr. Ayşe Yılmaz", specialty_code="ortodonti"),
        IntakeDoctor(full_name="Dr. Mehmet Demir", specialty_code="endodonti"),
    ),
    services=(
        IntakeService(name="Ortodonti Muayenesi", description="Tel/şeffaf plak değerlendirmesi"),
        IntakeService(name="Kanal Tedavisi", description="Endodontik tedavi"),
        IntakeService(name="Genel Muayene", description="Rutin diş kontrolü"),
    ),
    staff=(
        IntakeStaff(
            full_name="Klinik Sahibi",
            email="sahip@demo-dis-klinigi.example",
            role="owner",
            initial_password="pilot-owner-2026",
        ),
        IntakeStaff(
            full_name="Ön Büro Operatörü",
            email="operator@demo-dis-klinigi.example",
            role="operator",
            initial_password="pilot-operator-2026",
        ),
        IntakeStaff(
            full_name="Dr. Ayşe Yılmaz",
            email="ayse@demo-dis-klinigi.example",
            role="clinician",
            initial_password="pilot-hekim-2026",
        ),
    ),
)


def _second_clinic_intake() -> ClinicIntake:
    """İzolasyon kapısı için ikinci, bağımsız kiracı."""
    return ClinicIntake(
        name="İzole Kontrol Kliniği",
        slug="izole-kontrol-klinigi",
        kvkk_version="v1.0-pilot",
        kvkk_text="KVKK aydınlatma metni (ikinci kiracı, pilot taslak).",
        branches=(
            IntakeBranch(
                name="Tek Şube",
                address="Atatürk Blv. No:2, Çankaya/Ankara",
                phone="+90 312 000 00 00",
                working_hours={"mon": "09:00-17:00", "fri": "09:00-17:00"},
            ),
        ),
        doctors=(IntakeDoctor(full_name="Dr. Zeynep Kaya", specialty_code="periodontoloji"),),
        services=(IntakeService(name="Diş Eti Tedavisi"),),
        staff=(
            IntakeStaff(
                full_name="İkinci Sahip",
                email="sahip@izole-kontrol.example",
                role="owner",
                initial_password="pilot-owner2-2026",
            ),
        ),
    )


# ── Doğrulama ────────────────────────────────────────────────────────────────


def validate_intake(intake: ClinicIntake) -> list[str]:
    """Intake formunun yapısal sorunlarını döndürür; boş liste = geçerli."""
    issues: list[str] = []
    if not intake.name.strip():
        issues.append("Klinik adı boş olamaz.")
    if not SLUG_PATTERN.fullmatch(intake.slug) or not (3 <= len(intake.slug) <= 80):
        issues.append(f"Slug geçersiz: {intake.slug!r} (küçük harf/rakam/tire, 3-80 karakter).")
    if not intake.branches:
        issues.append("En az bir şube gerekli.")
    for branch in intake.branches:
        if not branch.working_hours:
            issues.append(f"Şube çalışma saatleri boş: {branch.name}.")
    if not intake.doctors:
        issues.append("En az bir hekim gerekli.")
    for doctor in intake.doctors:
        if doctor.specialty_code not in SPECIALTY_BY_CODE:
            issues.append(
                f"Hekim uzmanlık kodu ontolojide yok: {doctor.full_name} → {doctor.specialty_code!r}."
            )
    if not intake.services:
        issues.append("En az bir hizmet gerekli.")
    if not intake.kvkk_version.strip() or not intake.kvkk_text.strip():
        issues.append("KVKK aydınlatma metni ve versiyonu zorunlu.")
    roles = {member.role for member in intake.staff}
    if "owner" not in roles:
        issues.append("En az bir 'owner' personel gerekli.")
    unknown_roles = roles - set(_STAFF_ROLE_TO_MEMBERSHIP)
    if unknown_roles:
        issues.append(f"Bilinmeyen personel rolleri: {sorted(unknown_roles)}.")
    emails = [member.email for member in intake.staff]
    if len(emails) != len(set(emails)):
        issues.append("Personel e-postaları tekil olmalı.")
    for member in intake.staff:
        if "@" not in member.email:
            issues.append(f"Geçersiz e-posta: {member.email!r}.")
        if len(member.initial_password) < MIN_PASSWORD_LENGTH:
            issues.append(f"Parola çok kısa (<{MIN_PASSWORD_LENGTH}): {member.email}.")
    if not (0.0 < intake.shadow_review_threshold <= intake.ai_auto_reply_threshold <= 1.0):
        issues.append("Eşik sırası bozuk: 0 < shadow ≤ auto_reply ≤ 1 olmalı.")
    if intake.shadow_review_threshold < SHADOW_SAFETY_FLOOR:
        issues.append(
            f"Shadow eşiği güvenlik tabanının altında: {intake.shadow_review_threshold} < {SHADOW_SAFETY_FLOOR}."
        )
    return issues


# ── İdempotent provizyon ─────────────────────────────────────────────────────


@dataclass
class ProvisionResult:
    clinic_id: int
    created: dict[str, int] = field(default_factory=dict)
    updated: dict[str, int] = field(default_factory=dict)

    @property
    def total_created(self) -> int:
        return sum(self.created.values())

    @property
    def total_updated(self) -> int:
        return sum(self.updated.values())

    def to_dict(self) -> dict:
        return {
            "clinic_id": self.clinic_id,
            "created": dict(sorted(self.created.items())),
            "updated": dict(sorted(self.updated.items())),
        }


def _bump(counter: dict[str, int], key: str) -> None:
    counter[key] = counter.get(key, 0) + 1


def _ensure_roles(db: Session) -> dict[RoleName, Role]:
    existing = {role.name: role for role in db.scalars(select(Role)).all()}
    descriptions = {
        RoleName.CUSTOMER: "Can create and view only their own requests.",
        RoleName.OPERATOR: "Can manage customer workflows and appointments.",
        RoleName.ADMIN: "Can view all records, users, and audit logs.",
    }
    for name, description in descriptions.items():
        if name not in existing:
            role = Role(name=name, description=description)
            db.add(role)
            existing[name] = role
    db.flush()
    return existing


def provision(db: Session, intake: ClinicIntake) -> ProvisionResult:
    """Intake'i tek çağrıda idempotent provizyon eder ve sayaçları döndürür.

    Çağıran doğrulamadan sorumludur (`validate_intake` boş dönmeli); burada
    yine de savunmacı bir kontrol yapılır.
    """
    issues = validate_intake(intake)
    if issues:
        raise ValueError("Intake geçersiz: " + " | ".join(issues))

    created: dict[str, int] = {}
    updated: dict[str, int] = {}
    roles = _ensure_roles(db)

    clinic = db.scalars(select(Clinic).where(Clinic.slug == intake.slug)).first()
    if clinic is None:
        clinic = Clinic(name=intake.name, slug=intake.slug)
        db.add(clinic)
        _bump(created, "clinic")
    desired_clinic = {
        "name": intake.name,
        "default_language": intake.default_language,
        "timezone": intake.timezone,
        "ai_auto_reply_threshold": intake.ai_auto_reply_threshold,
        "shadow_review_threshold": intake.shadow_review_threshold,
    }
    clinic_changed = False
    for attr, value in desired_clinic.items():
        if getattr(clinic, attr) != value:
            setattr(clinic, attr, value)
            clinic_changed = True
    if clinic_changed and "clinic" not in created:
        _bump(updated, "clinic")
    db.flush()

    for branch_intake in intake.branches:
        branch = db.scalars(
            select(ClinicBranch).where(
                ClinicBranch.clinic_id == clinic.id, ClinicBranch.name == branch_intake.name
            )
        ).first()
        if branch is None:
            branch = ClinicBranch(clinic_id=clinic.id, name=branch_intake.name)
            db.add(branch)
            _bump(created, "branch")
        desired = {
            "address": branch_intake.address,
            "phone": branch_intake.phone,
            "working_hours_json": dict(branch_intake.working_hours),
        }
        changed = False
        for attr, value in desired.items():
            if getattr(branch, attr) != value:
                setattr(branch, attr, value)
                changed = True
        if changed and branch.id is not None:
            _bump(updated, "branch")

    for doctor_intake in intake.doctors:
        specialty_display = SPECIALTY_BY_CODE[doctor_intake.specialty_code].display_tr
        doctor = db.scalars(
            select(Doctor).where(
                Doctor.clinic_id == clinic.id, Doctor.full_name == doctor_intake.full_name
            )
        ).first()
        if doctor is None:
            doctor = Doctor(
                clinic_id=clinic.id,
                full_name=doctor_intake.full_name,
                specialty=specialty_display,
                is_active=doctor_intake.is_active,
            )
            db.add(doctor)
            _bump(created, "doctor")
        elif doctor.specialty != specialty_display or doctor.is_active != doctor_intake.is_active:
            doctor.specialty = specialty_display
            doctor.is_active = doctor_intake.is_active
            _bump(updated, "doctor")

    for service_intake in intake.services:
        service = db.scalars(
            select(ClinicService).where(
                ClinicService.clinic_id == clinic.id, ClinicService.name == service_intake.name
            )
        ).first()
        if service is None:
            db.add(
                ClinicService(
                    clinic_id=clinic.id,
                    name=service_intake.name,
                    description=service_intake.description or None,
                )
            )
            _bump(created, "service")
        elif service.description != (service_intake.description or None):
            service.description = service_intake.description or None
            _bump(updated, "service")

    for member in intake.staff:
        user = db.scalars(select(User).where(User.email == member.email)).first()
        if user is None:
            user = User(
                full_name=member.full_name,
                email=member.email,
                hashed_password=hash_password(member.initial_password),
                locale=intake.default_language,
                role_id=roles[_STAFF_ROLE_TO_USER_ROLE[member.role]].id,
            )
            db.add(user)
            _bump(created, "user")
        elif user.full_name != member.full_name:
            # Parola idempotent akışta yeniden yazılmaz; sıfırlama ayrı bir yönetim işlemidir.
            user.full_name = member.full_name
            _bump(updated, "user")
        db.flush()

        membership = db.scalars(
            select(ClinicMembership).where(
                ClinicMembership.clinic_id == clinic.id, ClinicMembership.user_id == user.id
            )
        ).first()
        desired_role = _STAFF_ROLE_TO_MEMBERSHIP[member.role]
        if membership is None:
            db.add(ClinicMembership(clinic_id=clinic.id, user_id=user.id, role=desired_role))
            _bump(created, "membership")
        elif membership.role != desired_role:
            membership.role = desired_role
            _bump(updated, "membership")

    active_disclosures = db.scalars(
        select(KVKKDisclosureVersion).where(
            KVKKDisclosureVersion.clinic_id == clinic.id,
            KVKKDisclosureVersion.is_active.is_(True),
        )
    ).all()
    current = next(
        (d for d in active_disclosures if d.version == intake.kvkk_version and d.disclosure_text == intake.kvkk_text),
        None,
    )
    if current is None:
        for disclosure in active_disclosures:
            disclosure.is_active = False
            _bump(updated, "kvkk_disclosure")
        db.add(
            KVKKDisclosureVersion(
                clinic_id=clinic.id,
                version=intake.kvkk_version,
                disclosure_text=intake.kvkk_text,
                is_active=True,
            )
        )
        _bump(created, "kvkk_disclosure")

    db.commit()
    return ProvisionResult(clinic_id=clinic.id, created=created, updated=updated)


# ── Kabul kontrolleri (playbook senaryolarının fonksiyon-seviyesi kısmı) ────


def _acceptance_checks(db: Session, clinic_id: int, intake: ClinicIntake) -> dict[str, dict]:
    clinic = db.get(Clinic, clinic_id)
    active_disclosure = db.scalars(
        select(KVKKDisclosureVersion).where(
            KVKKDisclosureVersion.clinic_id == clinic_id,
            KVKKDisclosureVersion.is_active.is_(True),
        )
    ).all()
    doctors = db.scalars(
        select(Doctor).where(Doctor.clinic_id == clinic_id, Doctor.is_active.is_(True))
    ).all()
    services = db.scalars(select(ClinicService).where(ClinicService.clinic_id == clinic_id)).all()
    branches = db.scalars(select(ClinicBranch).where(ClinicBranch.clinic_id == clinic_id)).all()
    memberships = db.scalars(
        select(ClinicMembership).where(ClinicMembership.clinic_id == clinic_id)
    ).all()
    membership_roles = {m.role for m in memberships}

    emergency = triage("Diş çekiminden sonra kanama bir türlü durmuyor")
    masked = mask_identifiers("Kimlik numaram 12345678901, telefonum 0532 111 22 33")
    vague = decide("iyi günler size bir şey soracaktım")

    return {
        "kvkk_versioned": {
            "scenario": "10 — KVKK metni versiyonlu ve aktif",
            "active_versions": sorted(d.version for d in active_disclosure),
            "pass": len(active_disclosure) == 1 and active_disclosure[0].version == intake.kvkk_version,
        },
        "emergency_escalation": {
            "scenario": "3 — acil kanama insana yükselir",
            "urgency": emergency.urgency.value,
            "pass": emergency.urgency is UrgencyLevel.EMERGENCY and emergency.requires_escalation,
        },
        "identity_masking": {
            "scenario": "4 — TC/telefon ham yankılanmaz",
            "pass": "12345678901" not in masked and "111 22 33" not in masked,
        },
        "ambiguous_abstains": {
            "scenario": "6 — belirsiz şikâyet çekimser/insan incelemesine gider",
            "abstain_reasons": list(vague.abstain_reasons),
            "pass": vague.escalate_to_human,
        },
        "booking_prereqs": {
            "scenario": "2 — randevu önkoşulları: aktif hekim + hizmet + çalışma saatli şube",
            "doctors": len(doctors),
            "services": len(services),
            "branches": len(branches),
            "pass": bool(doctors) and bool(services) and all(b.working_hours_json for b in branches),
        },
        "staff_access": {
            "scenario": "7/8 — operatör paneli + hekim shadow review rolleri tanımlı",
            "roles": sorted(role.value for role in membership_roles),
            "pass": ClinicUserRole.OWNER in membership_roles,
        },
        "safety_thresholds": {
            "scenario": "6 — düşük-güven shadow review eşiği güvenlik tabanında",
            "shadow": clinic.shadow_review_threshold,
            "auto_reply": clinic.ai_auto_reply_threshold,
            "pass": (
                clinic.shadow_review_threshold >= SHADOW_SAFETY_FLOOR
                and clinic.ai_auto_reply_threshold >= clinic.shadow_review_threshold
            ),
        },
    }


# ── Rapor ────────────────────────────────────────────────────────────────────


def _memory_session() -> Session:
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


def build_report() -> dict:
    """Provizyon otomasyonunun tüm kapılarını bellek-içi SQLite'ta koşturur."""
    intake = DEMO_INTAKE
    issues = validate_intake(intake)

    db = _memory_session()
    started = time.perf_counter()
    first = provision(db, intake)
    provision_seconds = time.perf_counter() - started
    second = provision(db, intake)
    other = provision(db, _second_clinic_intake())

    expected_created = {
        "clinic": 1,
        "branch": len(intake.branches),
        "doctor": len(intake.doctors),
        "service": len(intake.services),
        "user": len(intake.staff),
        "membership": len(intake.staff),
        "kvkk_disclosure": 1,
    }

    demo_doctors_after_other = db.scalars(
        select(Doctor).where(Doctor.clinic_id == first.clinic_id)
    ).all()
    cross_rows = db.scalars(
        select(Doctor).where(Doctor.clinic_id.notin_([first.clinic_id, other.clinic_id]))
    ).all()

    acceptance = _acceptance_checks(db, first.clinic_id, intake)
    db.close()

    gates = {
        "intake_validation": {
            "target": "intake formu yapısal olarak geçerli",
            "issues": issues,
            "pass": not issues,
        },
        "single_command_provision": {
            "target": "tek çağrıda tüm kayıtlar oluşur",
            "expected_created": expected_created,
            "created": first.to_dict()["created"],
            "pass": first.to_dict()["created"] == expected_created,
        },
        "idempotency": {
            "target": "aynı intake ikinci koşuda hiçbir şey oluşturmaz/değiştirmez",
            "second_run_created": first_pass_zero(second.created),
            "second_run_updated": first_pass_zero(second.updated),
            "pass": second.total_created == 0 and second.total_updated == 0,
        },
        "tenant_isolation": {
            "target": "ikinci kiracının provizyonu ilk kliniğin verisine dokunmaz",
            "demo_doctor_count": len(demo_doctors_after_other),
            "orphan_rows": len(cross_rows),
            "pass": len(demo_doctors_after_other) == len(intake.doctors) and not cross_rows,
        },
        "acceptance_scenarios": {
            "target": "playbook kabul senaryolarının fonksiyon-seviyesi kısmı geçer",
            "checks": acceptance,
            "pass": all(check["pass"] for check in acceptance.values()),
        },
        "time_budget": {
            "target": "otomatik provizyon playbook bütçesinin (6 saat) çok altında",
            "budget_seconds": TIME_BUDGET_SECONDS,
            "pass": provision_seconds < TIME_BUDGET_SECONDS,
        },
    }
    return {
        "name": "ip6_2_onboarding_provision",
        "intake_slug": intake.slug,
        "provision_counts": first.to_dict(),
        "gates": gates,
        "overall_pass": all(gate["pass"] for gate in gates.values()),
        "remaining": [
            "Pilot klinikte kronometreli gerçek kurulum (<6 saat) doğrulaması.",
            "Gerçek WhatsApp/telefon kanal bağlama izinleri.",
            "Avukat onaylı nihai KVKK aydınlatma metni (pilot taslak yerine).",
            "Gerçek HBYS/takvim adapteri (İP-5.2 kapsamı).",
        ],
    }


def first_pass_zero(counter: dict[str, int]) -> dict[str, int]:
    """Rapor için sayaç kopyası (boşsa boş sözlük — artefakt deterministik)."""
    return dict(sorted(counter.items()))


def render(report: dict) -> str:
    ok = lambda value: "PASS" if value else "FAIL"  # noqa: E731
    lines = [
        "İP-6.2 — Tek Komut Klinik Onboarding Provizyonu",
        "=" * 60,
        f"Intake: {report['intake_slug']} → klinik #{report['provision_counts']['clinic_id']}",
    ]
    for key, gate in report["gates"].items():
        lines.append(f"{ok(gate['pass']):<5} {key:<26} {gate['target']}")
    for name, check in report["gates"]["acceptance_scenarios"]["checks"].items():
        lines.append(f"      {ok(check['pass']):<5} kabul/{name:<20} {check['scenario']}")
    lines += [
        "-" * 60,
        f"GENEL: {ok(report['overall_pass'])}",
        "Kalan:",
    ]
    lines.extend(f"- {item}" for item in report["remaining"])
    return "\n".join(lines)


def write_artifact(report: dict, path: Path = ARTIFACT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="İP-6.2 tek komut klinik onboarding provizyonu")
    parser.add_argument("--no-save", action="store_true", help="artefakt yazma")
    parser.add_argument("--json", action="store_true", help="JSON çıktısı")
    args = parser.parse_args(argv)

    report = build_report()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render(report))
    if not args.no_save:
        path = write_artifact(report)
        if not args.json:
            print(f"\nArtefakt: {path}")
    return 0 if report["overall_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
