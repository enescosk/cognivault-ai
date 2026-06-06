"""
Public (anonim hasta) endpoint'leri.

Patient page için tasarlanmıştır. Hiçbir kullanıcı login'i gerekmez; bunun
yerine iki kısa-ömürlü token (consent + session) ile yetkilendirme yapılır.
Detaylar için: `docs/product/patient-clinic-experience.md` §5.3

Akış:
  1.  GET  /api/public/clinics/{slug}                          (anonim)
  2.  POST /api/public/clinics/{slug}/consent                  (anonim → consent_token)
  3.  POST /api/public/clinics/{slug}/conversations            (consent_token → session_token)
  4.  POST /api/public/clinics/{slug}/conversations/{id}/messages   (session_token)
  5.  POST /api/public/clinics/{slug}/conversations/{id}/appointments (session_token)

Rate limit: IP başına saatlik 30 mesaj (Faz 1.5'te slowapi ile).
"""

from __future__ import annotations

import hashlib
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.ai.voice_factory import get_stt_provider, get_tts_provider
from app.core.config import get_settings

from app.api.dependencies import get_db
from app.models import (
    ClinicalAppointment,
    ClinicalAppointmentStatus,
    ClinicalSlotOffer,
    Clinic,
    ClinicBranch,
    ClinicChannel,
    ClinicConversation,
    ClinicMessage,
    ClinicMessageSender,
    ClinicPatient,
    ConsentRecord,
    ConsentType,
)
from app.services import patient_session
from app.services.clinical_service import (
    IncomingClinicalMessage,
    ingest_clinical_message,
    normalize_phone,
)
from app.services.clinical_slot_service import (
    build_public_slot_offers,
    consume_held_slot_offer,
    hold_slot_offer,
)

router = APIRouter(prefix="/public", tags=["public-patient"])


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic schemas — patient-facing minimal payload'lar
# ─────────────────────────────────────────────────────────────────────────────


class PublicBranchView(BaseModel):
    name: str
    address: str | None = None
    phone: str | None = None
    working_hours: dict | None = None


class PublicDisclosureView(BaseModel):
    version: str
    body_hash: str
    headline: str


class PublicClinicView(BaseModel):
    slug: str
    name: str
    headline: str
    sub_headline: str
    logo_url: str | None = None
    primary_color: str
    accent_color: str
    contact_phone: str | None = None
    public_address: str | None = None
    branches: list[PublicBranchView]
    services: list[str]
    disclosure: PublicDisclosureView


class ConsentRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    phone: str | None = Field(default=None, min_length=6, max_length=40)
    disclosure_version: str = Field(min_length=1, max_length=32)
    disclosure_hash: str = Field(min_length=8, max_length=128)
    accepted_cross_border: bool = Field(
        default=False,
        description="WhatsApp / Twilio gibi yurt dışı işleyiciler için ayrı m.9 onayı.",
    )


class ConsentResponse(BaseModel):
    consent_token: str
    expires_in_seconds: int


class StartConversationRequest(BaseModel):
    initial_message: str | None = Field(default=None, max_length=2000)


class StartConversationResponse(BaseModel):
    session_token: str
    conversation_id: int
    patient_id: int
    welcome_message: str | None = None


class PublicMessageRequest(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class PublicMessageView(BaseModel):
    id: int
    sender: str
    body: str
    intent: str | None
    confidence_score: float | None
    metadata_json: dict | None
    created_at: datetime


class PublicSlotOfferView(BaseModel):
    id: int
    department: str
    physician_name: str | None
    starts_at: datetime
    ends_at: datetime | None
    status: str
    expires_at: datetime
    label: str
    metadata_json: dict | None


class PublicMessageResponse(BaseModel):
    patient_message: PublicMessageView
    assistant_message: PublicMessageView | None
    requires_human_review: bool
    conversation_status: str
    slot_offers: list[PublicSlotOfferView] = []
    # Rehberli akış için üst seviye sinyaller — mesaj shadow review'a düşüp
    # assistant_message None olsa bile intent/branş/acil bilgisi buradan okunur.
    detected_intent: str | None = None
    specialty: str | None = None
    emergency: bool = False


class PublicSlotHoldResponse(BaseModel):
    slot_offer: PublicSlotOfferView


class PublicAppointmentConfirmRequest(BaseModel):
    department: str = Field(min_length=2, max_length=140)
    slot_offer_id: int
    notes: str | None = Field(default=None, max_length=2000)


class PublicAppointmentConfirmResponse(BaseModel):
    appointment_id: int
    status: str
    starts_at: datetime | None
    department: str
    summary: str


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _branding_or_default(clinic: Clinic) -> dict:
    """Klinik branding'i settings_json'dan oku, eksik alanları default'la."""
    raw = (clinic.settings_json or {}).get("branding") or {}
    return {
        "headline": raw.get("headline") or f"{clinic.name} AI Resepsiyonu",
        "sub_headline": raw.get("sub_headline")
        or "KVKK onayınızla, AI asistanımız üzerinden saniyeler içinde randevu alın.",
        "logo_url": raw.get("logo_url"),
        "primary_color": raw.get("primary_color") or "#1f3b73",
        "accent_color": raw.get("accent_color") or "#28c8a6",
        "contact_phone": raw.get("contact_phone"),
        "public_address": raw.get("public_address"),
        "services": list(raw.get("services") or []) or [
            "Genel Diş Hekimliği",
            "Endodonti",
            "Ortodonti",
            "İmplantoloji",
            "Estetik Diş Hekimliği",
            "Dermatoloji",
            "Medikal Estetik",
        ],
    }


def _disclosure_or_default(clinic: Clinic) -> dict:
    """KVKK aydınlatma metnini settings_json'dan oku, yoksa default v0 üret."""
    disclosures = (clinic.settings_json or {}).get("kvkk_disclosures") or []
    active = next((d for d in disclosures if d.get("is_active")), None)
    if active is None and disclosures:
        active = disclosures[-1]
    if active is None:
        default_body = (
            f"{clinic.name} AI Resepsiyonu KVKK Aydınlatma Metni\n\n"
            "1. Veri Sorumlusu: " + clinic.name + "\n"
            "2. İşlenen veriler: ad-soyad, telefon, sağlık şikayeti metni.\n"
            "3. Amaç: Randevu yönetimi ve hasta bilgilendirmesi.\n"
            "4. Yurt dışı aktarımı: yapılmaz; veriler yerel sunucularımızda işlenir.\n"
            "5. Haklarınız: 6698 sayılı KVKK m.11'de belirtilen tüm haklara sahipsiniz.\n"
        )
        body_hash = hashlib.sha256(default_body.encode("utf-8")).hexdigest()
        active = {
            "version": "v0-implicit",
            "body": default_body,
            "body_hash": body_hash,
            "is_active": True,
            "headline": "KVKK Aydınlatma — Lütfen Okuyup Onaylayın",
        }
    return active


def _find_clinic_by_slug(db: Session, slug: str) -> Clinic:
    clinic = db.scalars(
        select(Clinic).options(selectinload(Clinic.branches)).where(Clinic.slug == slug)
    ).first()
    if clinic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="clinic_not_found")
    return clinic


def _extract_bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing_patient_token",
        )
    return authorization.split(" ", 1)[1].strip()


def _ip_or_device_hint(request: Request) -> str:
    # Trust X-Forwarded-For first (proxy), then remote
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()[:120]
    return (request.client.host if request.client else "unknown")[:120]


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint 1 — Klinik public görünümü
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/clinics/{slug}", response_model=PublicClinicView)
def get_public_clinic(slug: str, db: Session = Depends(get_db)) -> PublicClinicView:
    clinic = _find_clinic_by_slug(db, slug)
    branding = _branding_or_default(clinic)
    disclosure = _disclosure_or_default(clinic)
    return PublicClinicView(
        slug=clinic.slug,
        name=clinic.name,
        headline=branding["headline"],
        sub_headline=branding["sub_headline"],
        logo_url=branding["logo_url"],
        primary_color=branding["primary_color"],
        accent_color=branding["accent_color"],
        contact_phone=branding["contact_phone"],
        public_address=branding["public_address"],
        branches=[
            PublicBranchView(
                name=b.name,
                address=b.address,
                phone=b.phone,
                working_hours=b.working_hours_json,
            )
            for b in clinic.branches
        ],
        services=branding["services"],
        disclosure=PublicDisclosureView(
            version=disclosure["version"],
            body_hash=disclosure["body_hash"],
            headline=disclosure.get("headline") or "KVKK Aydınlatma — Lütfen Okuyup Onaylayın",
        ),
    )


@router.get("/clinics/{slug}/disclosure")
def get_public_disclosure(slug: str, db: Session = Depends(get_db)) -> dict:
    """Tam aydınlatma metni — modal'da "tam metni oku" link'i bunu açar."""
    clinic = _find_clinic_by_slug(db, slug)
    disclosure = _disclosure_or_default(clinic)
    return {
        "version": disclosure["version"],
        "body_hash": disclosure["body_hash"],
        "headline": disclosure.get("headline"),
        "body": disclosure["body"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint 2 — KVKK onayı al, consent_token döndür
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/clinics/{slug}/consent", response_model=ConsentResponse)
def submit_patient_consent(
    slug: str,
    payload: ConsentRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> ConsentResponse:
    clinic = _find_clinic_by_slug(db, slug)
    disclosure = _disclosure_or_default(clinic)

    # Versiyon ve hash tutarlılığı kontrolü — frontend metnin SHA256'sını gönderir
    if payload.disclosure_version != disclosure["version"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="disclosure_version_mismatch",
        )
    if payload.disclosure_hash.lower() != disclosure["body_hash"].lower():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="disclosure_hash_mismatch",
        )

    # ConsentRecord — patient_id henüz yok, conversation oluştururken bağlanacak
    consent = ConsentRecord(
        clinic_id=clinic.id,
        patient_id=None,
        conversation_id=None,
        consent_type=ConsentType.DATA_PROCESSING,
        granted=True,
        channel=ClinicChannel.WEB_CHAT,
        ip_or_device_hint=_ip_or_device_hint(request),
        consent_text_version=disclosure["version"],
    )
    db.add(consent)
    consent_records = [consent]

    # Cross-border ayrı tipte ayrı satır
    if payload.accepted_cross_border:
        cross_border = ConsentRecord(
            clinic_id=clinic.id,
            patient_id=None,
            conversation_id=None,
            consent_type=ConsentType.CROSS_BORDER_TRANSFER,
            granted=True,
            channel=ClinicChannel.WEB_CHAT,
            ip_or_device_hint=_ip_or_device_hint(request),
            consent_text_version=disclosure["version"],
        )
        db.add(cross_border)
        consent_records.append(cross_border)

    db.flush()
    consent_record_ids = [row.id for row in consent_records]
    db.commit()

    token = patient_session.issue_consent_token(
        clinic_id=clinic.id,
        clinic_slug=clinic.slug,
        disclosure_version=disclosure["version"],
        consent_record_ids=consent_record_ids,
    )
    # Body'deki name/phone şu an consent satırına yazılmıyor — patient
    # ConsentRecord değil ClinicPatient tablosunda yaşıyor; consent token
    # ile gelecek conversation start'ta birleştirilecek.
    return ConsentResponse(
        consent_token=token,
        expires_in_seconds=patient_session.CONSENT_TOKEN_TTL_MIN * 60,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint 3 — Conversation başlat (consent_token → session_token + initial AI reply)
# ─────────────────────────────────────────────────────────────────────────────


def _resolve_or_create_patient(
    db: Session, clinic: Clinic, full_name: str | None, phone: str | None
) -> ClinicPatient:
    """Var olan hastayı bul, yoksa yarat. Kimlik eksikse anonim placeholder yarat.

    Yeni akışta hastalar onboarding form'undan değil, doğrudan chat'ten geliyor.
    Identity AI ile sohbet sırasında toplanacak (set_patient_identity tool'u).
    Bu yüzden anonim placeholder telefon `anon-<uuid>` formatında.
    """
    import uuid as _uuid

    if phone:
        normalized = normalize_phone(phone)
        patient = db.scalars(
            select(ClinicPatient).where(
                ClinicPatient.clinic_id == clinic.id, ClinicPatient.phone == normalized
            )
        ).first()
        if patient is not None:
            if full_name and not patient.full_name:
                patient.full_name = full_name
                db.add(patient)
                db.commit()
                db.refresh(patient)
            return patient
    else:
        # Anonim hasta: AI tool sonradan set_patient_identity ile doldurur.
        normalized = f"anon-{_uuid.uuid4().hex[:12]}"

    patient = ClinicPatient(
        clinic_id=clinic.id,
        full_name=full_name,
        phone=normalized,
        language=clinic.default_language or "tr",
        source=ClinicChannel.WEB_CHAT,
        external_ref=normalized,
        metadata_json={"source": "patient_page", "anonymous": not bool(phone)},
    )
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return patient


class PatientIdentityRequest(BaseModel):
    """Conversation başlatmak için body. Yeni akışta tüm alanlar opsiyonel —
    kimlik AI ile sohbet sırasında set_patient_identity tool'uyla toplanacak.
    Geri uyumluluk: legacy clientlar full_name+phone gönderebiliyor."""

    full_name: str | None = Field(default=None, max_length=160)
    phone: str | None = Field(default=None, max_length=40)
    initial_message: str | None = Field(default=None, max_length=2000)


@router.post("/clinics/{slug}/conversations", response_model=StartConversationResponse)
def start_patient_conversation(
    slug: str,
    payload: PatientIdentityRequest,
    request: Request,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
) -> StartConversationResponse:
    token = _extract_bearer(authorization)
    consent = patient_session.decode_consent_token(token)
    if consent.clinic_slug != slug:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="consent_clinic_mismatch"
        )

    clinic = _find_clinic_by_slug(db, slug)
    if clinic.id != consent.clinic_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="consent_clinic_mismatch"
        )

    patient = _resolve_or_create_patient(db, clinic, payload.full_name, payload.phone)

    # Bekleyen anonim consent satırlarını bu patient_id'ye bağla
    anon_rows = db.scalars(
        select(ConsentRecord).where(
            ConsentRecord.clinic_id == clinic.id,
            ConsentRecord.id.in_(consent.consent_record_ids or (-1,)),
            ConsentRecord.patient_id.is_(None),
        )
    ).all()
    for row in anon_rows:
        row.patient_id = patient.id
        db.add(row)
    db.commit()

    # Yeni akış: hasta initial_message vermezse boş bir conversation yarat
    # + proactive AI greeting'i system mesajı olarak göster.
    # Initial message varsa eski akış gibi ingest et.
    if payload.initial_message and payload.initial_message.strip():
        incoming = IncomingClinicalMessage(
            channel=ClinicChannel.WEB_CHAT,
            from_phone=patient.phone,
            body=payload.initial_message.strip(),
            patient_name=patient.full_name,
            external_message_id=None,
            external_thread_id=patient.phone,
            raw_payload={"source": "patient_page", "consent_version": consent.disclosure_version},
        )
        result = ingest_clinical_message(db, incoming, clinic=clinic)
        conversation = result.conversation
        welcome = result.reply
    else:
        # Boş conversation + proactive welcome.
        conversation = ClinicConversation(
            clinic_id=clinic.id,
            patient_id=patient.id,
            channel=ClinicChannel.WEB_CHAT,
            language=clinic.default_language or "tr",
            metadata_json={"source": "patient_page", "consent_version": consent.disclosure_version},
        )
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
        # AI'dan proactive karşılama mesajı (assistant olarak yaz)
        welcome = _build_proactive_welcome(clinic, patient)
        greeting = ClinicMessage(
            clinic_id=clinic.id,
            conversation_id=conversation.id,
            sender=ClinicMessageSender.ASSISTANT,
            content=welcome,
            language=clinic.default_language or "tr",
            metadata_json={
                "action": "proactive_welcome",
                "channel": ClinicChannel.WEB_CHAT.value,
                "anonymous_patient": not bool(payload.phone),
            },
        )
        db.add(greeting)
        db.commit()

    # Anonim consent'leri conversation'a da bağla
    for row in db.scalars(
        select(ConsentRecord).where(
            ConsentRecord.clinic_id == clinic.id,
            ConsentRecord.patient_id == patient.id,
            ConsentRecord.conversation_id.is_(None),
        )
    ).all():
        row.conversation_id = conversation.id
        db.add(row)
    db.commit()

    session_token = patient_session.issue_session_token(
        clinic_id=clinic.id,
        clinic_slug=clinic.slug,
        patient_id=patient.id,
        conversation_id=conversation.id,
        disclosure_version=consent.disclosure_version,
    )

    return StartConversationResponse(
        session_token=session_token,
        conversation_id=conversation.id,
        patient_id=patient.id,
        welcome_message=welcome,
    )


def _build_proactive_welcome(clinic: Clinic, patient: ClinicPatient) -> str:
    """AI'ın chat'i açan ilk mesajı.

    Bölüm A1 referansı: hasta sayfayı açar açmaz "ne yapacağımı biliyorum"
    hissi alır; AI önce kendini tanıtır, sonra hastayı serbest bırakır.
    """
    persona_name = "Selin"  # Faz 3.5'te clinical_persona_service'ten seçilecek
    name_addr = f"{patient.full_name}, " if patient.full_name else ""
    return (
        f"Merhaba {name_addr}ben {persona_name}, {clinic.name} AI asistanı. "
        "Size nasıl yardımcı olabilirim?\n\n"
        "• Randevu almak istiyorsanız şikayetinizi ve tercih ettiğiniz "
        "gün/saati yazabilirsiniz.\n"
        "• Acil bir sağlık sorununuz varsa lütfen vakit kaybetmeden "
        "112'yi arayın."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint 4 — Mesaj gönder
# ─────────────────────────────────────────────────────────────────────────────


def _message_view(m: ClinicMessage) -> PublicMessageView:
    return PublicMessageView(
        id=m.id,
        sender=m.sender.value if hasattr(m.sender, "value") else str(m.sender),
        body=m.content,
        intent=m.intent.value if m.intent else None,
        confidence_score=m.confidence_score,
        metadata_json=m.metadata_json,
        created_at=m.created_at,
    )


def _slot_offer_view(offer: ClinicalSlotOffer) -> PublicSlotOfferView:
    starts_at = offer.starts_at if offer.starts_at.tzinfo else offer.starts_at.replace(tzinfo=timezone.utc)
    local_label = starts_at.astimezone(timezone.utc).strftime("%d.%m.%Y %H:%M")
    doctor = f" · {offer.physician_name}" if offer.physician_name else ""
    return PublicSlotOfferView(
        id=offer.id,
        department=offer.department,
        physician_name=offer.physician_name,
        starts_at=offer.starts_at,
        ends_at=offer.ends_at,
        status=offer.status.value if hasattr(offer.status, "value") else str(offer.status),
        expires_at=offer.expires_at,
        label=f"{local_label}{doctor}",
        metadata_json=offer.metadata_json,
    )


def _get_scoped_patient_and_conversation(
    db: Session,
    *,
    slug: str,
    conversation_id: int,
    authorization: str | None,
) -> tuple[Clinic, patient_session.SessionPayload, ClinicPatient, ClinicConversation]:
    token = _extract_bearer(authorization)
    session = patient_session.decode_session_token(token)
    if session.clinic_slug != slug or session.conversation_id != conversation_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="session_scope_mismatch"
        )

    clinic = _find_clinic_by_slug(db, slug)
    if clinic.id != session.clinic_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="session_scope_mismatch"
        )
    patient = db.get(ClinicPatient, session.patient_id)
    if patient is None or patient.clinic_id != clinic.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="patient_not_found")
    conversation = db.get(ClinicConversation, session.conversation_id)
    if (
        conversation is None
        or conversation.clinic_id != clinic.id
        or conversation.patient_id != patient.id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="conversation_not_found"
        )
    return clinic, session, patient, conversation


@router.post(
    "/clinics/{slug}/conversations/{conversation_id}/messages",
    response_model=PublicMessageResponse,
)
def send_patient_message(
    slug: str,
    conversation_id: int,
    payload: PublicMessageRequest,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
) -> PublicMessageResponse:
    clinic, session, patient, conversation = _get_scoped_patient_and_conversation(
        db, slug=slug, conversation_id=conversation_id, authorization=authorization
    )

    incoming = IncomingClinicalMessage(
        channel=ClinicChannel.WEB_CHAT,
        from_phone=patient.phone,
        body=payload.body,
        patient_name=patient.full_name,
        external_message_id=None,
        external_thread_id=patient.phone,
        conversation_id=conversation.id,
        raw_payload={"source": "patient_page"},
    )
    # Hasta sayfası rehberli akışı LLM cevabını kullanmıyor (intent + branş + slot
    # kural-tabanlı yeterli). use_ai=False → ~anında döner, lokal LLM beklenmez.
    result = ingest_clinical_message(db, incoming, clinic=clinic, use_ai=False)

    # En son hasta + asistan mesajı çek
    msgs = sorted(result.conversation.messages, key=lambda m: m.created_at)
    last_patient = next((m for m in reversed(msgs) if m.sender == ClinicMessageSender.PATIENT), None)
    last_assistant = next(
        (m for m in reversed(msgs) if m.sender == ClinicMessageSender.ASSISTANT), None
    )
    slot_offers: list[ClinicalSlotOffer] = []
    assistant_intent = (
        getattr(last_assistant.intent, "value", str(last_assistant.intent))
        if last_assistant is not None and last_assistant.intent
        else None
    )
    shadow_intent = (
        getattr(result.shadow_review.intent, "value", str(result.shadow_review.intent))
        if result.shadow_review is not None
        else None
    )
    if assistant_intent == "book_appointment":
        data = (last_assistant.metadata_json or {}).get("data") or {}
        slot_offers = build_public_slot_offers(
            db,
            clinic=clinic,
            patient=patient,
            conversation=result.conversation,
            slot_decision=data.get("slot_decision") or {},
        )
    elif (
        shadow_intent == "book_appointment"
        and result.shadow_review is not None
        and result.shadow_review.confidence_score >= 0.78
    ):
        data = (result.shadow_review.metadata_json or {}).get("data") or {}
        slot_offers = build_public_slot_offers(
            db,
            clinic=clinic,
            patient=patient,
            conversation=result.conversation,
            slot_decision=data.get("slot_decision") or {},
        )

    # Üst seviye sinyaller: assistant ya da shadow review hangisindeyse oradan al.
    detected_intent = assistant_intent or shadow_intent
    # "data" anahtarı olan ilk kaynağı seç: auto-reply mesajı data taşır; shadow'da
    # taslak mesaj data taşımaz ama ShadowReview taşır.
    _metas = [
        last_assistant.metadata_json if last_assistant is not None else None,
        result.shadow_review.metadata_json if result.shadow_review is not None else None,
    ]
    chosen_meta = next((m for m in _metas if m and m.get("data")), {})
    intake_meta = (chosen_meta.get("data") or {}).get("intake") or {}
    specialty = intake_meta.get("specialty")
    emergency = detected_intent == "medical_emergency"

    return PublicMessageResponse(
        patient_message=_message_view(last_patient) if last_patient else _message_view(result.message),
        assistant_message=_message_view(last_assistant) if last_assistant else None,
        requires_human_review=result.action == "shadow_review",
        conversation_status=result.conversation.status.value
        if hasattr(result.conversation.status, "value")
        else str(result.conversation.status),
        slot_offers=[_slot_offer_view(offer) for offer in slot_offers],
        detected_intent=detected_intent,
        specialty=specialty,
        emergency=emergency,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint 5 — Slot tut (slot picker UI'dan tetiklenir)
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/clinics/{slug}/conversations/{conversation_id}/slot-offers/{offer_id}/hold",
    response_model=PublicSlotHoldResponse,
)
def hold_patient_slot_offer(
    slug: str,
    conversation_id: int,
    offer_id: int,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
) -> PublicSlotHoldResponse:
    clinic, session, _patient, _conversation = _get_scoped_patient_and_conversation(
        db, slug=slug, conversation_id=conversation_id, authorization=authorization
    )
    try:
        offer = hold_slot_offer(
            db,
            clinic_id=clinic.id,
            patient_id=session.patient_id,
            conversation_id=conversation_id,
            offer_id=offer_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return PublicSlotHoldResponse(slot_offer=_slot_offer_view(offer))


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint 6 — Randevu oluştur (sadece held slot ile)
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/clinics/{slug}/conversations/{conversation_id}/appointments",
    response_model=PublicAppointmentConfirmResponse,
)
def confirm_patient_appointment(
    slug: str,
    conversation_id: int,
    payload: PublicAppointmentConfirmRequest,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
) -> PublicAppointmentConfirmResponse:
    clinic, session, _patient, conversation = _get_scoped_patient_and_conversation(
        db, slug=slug, conversation_id=conversation_id, authorization=authorization
    )
    try:
        offer = consume_held_slot_offer(
            db,
            clinic_id=clinic.id,
            patient_id=session.patient_id,
            conversation_id=conversation_id,
            offer_id=payload.slot_offer_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    appointment = ClinicalAppointment(
        clinic_id=clinic.id,
        patient_id=session.patient_id,
        conversation_id=conversation_id,
        branch_id=offer.branch_id,
        department=offer.department,
        starts_at=offer.starts_at,
        status=ClinicalAppointmentStatus.PENDING,
        notes=payload.notes,
        metadata_json={
            "source": "patient_page",
            "slot_offer_id": offer.id,
            "slot_offer_source": offer.source,
            "physician_name": offer.physician_name,
            "confirmed_via": "web_chat",
        },
    )
    db.add(appointment)

    # Konuşmayı kapanışa al
    if conversation is not None:
        from app.models import ClinicConversationStatus

        conversation.status = ClinicConversationStatus.APPOINTMENT_PENDING
        conversation.metadata_json = {
            **(conversation.metadata_json or {}),
            "last_appointment_id_pending": True,
        }
        db.add(conversation)

    db.commit()
    db.refresh(appointment)

    # ──── Bildirim gönderimi: hasta + doktor SMS'leri ─────────────────────
    # Mock mode (NOTIFICATION_PROVIDER yok) → konsola + log'a basar; gerçek
    # sağlayıcı geldiğinde adapter notification_service içinde değişir.
    from app.services.notification_service import (
        send_appointment_sms_to_doctor,
        send_appointment_sms_to_patient,
    )

    patient_full = db.get(ClinicPatient, session.patient_id)
    branding = (clinic.settings_json or {}).get("branding") or {}
    clinic_phone = branding.get("contact_phone")
    # Doktor telefonu admin paneli kurulana kadar klinik genel hattına düşer
    doctor_phone = branding.get("doctor_notification_phone") or clinic_phone
    complaint_summary = (conversation.metadata_json or {}).get("complaint_summary") if conversation else None

    if patient_full and not (patient_full.phone or "").startswith("anon-"):
        send_appointment_sms_to_patient(
            patient_phone=patient_full.phone,
            patient_name=patient_full.full_name,
            clinic_name=clinic.name,
            clinic_phone=clinic_phone,
            department=offer.department,
            physician_name=offer.physician_name,
            starts_at=offer.starts_at,
            confirmation_code=f"CV{appointment.id:06d}",
        )
    else:
        # Anonim hasta — AI kimliği toplayamamış, klinik ekibi takip etsin.
        import logging as _log
        _log.getLogger(__name__).info(
            "📱 [SMS-PATIENT] anonim hasta — SMS atlandı, klinik ekibi takipte | appointment=%s",
            appointment.id,
        )

    send_appointment_sms_to_doctor(
        doctor_phone=doctor_phone,
        doctor_name=offer.physician_name,
        clinic_name=clinic.name,
        patient_name=patient_full.full_name if patient_full else None,
        patient_phone=(patient_full.phone if patient_full else "anonim"),
        department=offer.department,
        starts_at=offer.starts_at,
        patient_complaint_summary=complaint_summary,
    )

    return PublicAppointmentConfirmResponse(
        appointment_id=appointment.id,
        status=appointment.status.value
        if hasattr(appointment.status, "value")
        else str(appointment.status),
        starts_at=appointment.starts_at,
        department=appointment.department,
        summary=(
            f"{offer.department} randevunuz {appointment.starts_at.strftime('%d.%m.%Y %H:%M')} "
            "için oluşturuldu. Onay SMS'i gönderildi; klinik personeli de bilgilendirildi."
        )
        if appointment.starts_at
        else f"{offer.department} randevu talebiniz oluşturuldu, klinik ekibimiz en kısa sürede sizinle iletişime geçecek.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint 7 — Patient identity update (AI tool veya UI kullanabilir)
# ─────────────────────────────────────────────────────────────────────────────


class PatientIdentityUpdateRequest(BaseModel):
    """AI sohbet içinde hastanın adını/telefonunu çıkardığında çağırılır.
    UI'dan da yedek input olarak kullanılabilir.
    """

    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    phone: str | None = Field(default=None, min_length=6, max_length=40)


class PatientIdentityResponse(BaseModel):
    patient_id: int
    full_name: str | None
    phone: str
    is_anonymous: bool


@router.patch(
    "/clinics/{slug}/conversations/{conversation_id}/patient",
    response_model=PatientIdentityResponse,
)
def update_patient_identity(
    slug: str,
    conversation_id: int,
    payload: PatientIdentityUpdateRequest,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
) -> PatientIdentityResponse:
    """Sohbet içinde hasta kimliğini günceller.

    Yeni akışta hasta chat ekranına anonim olarak başlıyor; ismini ve
    telefonunu AI sohbet sırasında topluyor. Bu endpoint AI tool çağrısının
    (set_patient_identity) veya UI bypass formunun yazdığı noktadır.

    Telefon güncellenirken aynı klinikte mevcut bir patient row'u varsa
    iki kayıt birleşmez (sadece anonim placeholder güncellenir).
    """
    clinic, session, patient, _conversation = _get_scoped_patient_and_conversation(
        db, slug=slug, conversation_id=conversation_id, authorization=authorization
    )

    changed = False
    if payload.full_name and not patient.full_name:
        patient.full_name = payload.full_name
        changed = True
    if payload.phone:
        normalized = normalize_phone(payload.phone)
        # Çakışmayı önle: aynı klinikte bu telefonla başka hasta var mı?
        clash = db.scalars(
            select(ClinicPatient).where(
                ClinicPatient.clinic_id == clinic.id,
                ClinicPatient.phone == normalized,
                ClinicPatient.id != patient.id,
            )
        ).first()
        if clash is None:
            patient.phone = normalized
            patient.external_ref = normalized
            meta = dict(patient.metadata_json or {})
            meta["anonymous"] = False
            patient.metadata_json = meta
            changed = True
        # Çakışma varsa sessiz geç — gerçek hayatta bunu chat üzerinden
        # operatöre haber vermek lazım; MVP'de placeholder kayda devam.

    if changed:
        db.add(patient)
        db.commit()
        db.refresh(patient)

    is_anonymous = (patient.phone or "").startswith("anon-")
    return PatientIdentityResponse(
        patient_id=patient.id,
        full_name=patient.full_name,
        phone=patient.phone,
        is_anonymous=is_anonymous,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Public ses — hasta sayfası sesli asistan. KVKK local-first: ses varsayılan
# olarak yurt içinde işlenir (TTS=Piper tr_TR, STT=faster-whisper). Anonim.
# ─────────────────────────────────────────────────────────────────────────────
class PublicSynthesizeRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1200)
    voice: str = "nova"


@router.post("/clinics/{slug}/voice/synthesize")
def public_synthesize_speech(slug: str, body: PublicSynthesizeRequest) -> StreamingResponse:
    """Hasta sayfası için metni doğal sese çevirir (varsayılan lokal Piper tr_TR).

    Auth gerekmez (anonim hasta akışı). Ses yurt içinde üretilir; klinik veri
    içermez — yalnızca asistanın söylediği metin.
    """
    text = body.text.strip()[:1200]
    if not text:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Metin boş.")
    try:
        audio_bytes, mime = get_tts_provider().synthesize(text, voice=body.voice)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=f"Ses sentezi hatası: {exc}") from exc

    ext = "wav" if mime == "audio/wav" else "mp3"
    return StreamingResponse(
        io.BytesIO(audio_bytes),
        media_type=mime,
        headers={"Content-Disposition": f"inline; filename=speech.{ext}"},
    )


@router.post("/clinics/{slug}/voice/transcribe")
async def public_transcribe_speech(
    slug: str,
    file: UploadFile,
    language: str = "tr",
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Hasta sayfası sesli görüşmesi için konuşmayı metne çevirir.

    Varsayılan lokal faster-whisper ile yurt içinde çözülür; ses verisi dışarı
    çıkmaz. Anonim (klinik slug doğrulanır).
    """
    clinic = db.scalars(select(Clinic).where(Clinic.slug == slug)).first()
    if clinic is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="clinic_not_found")
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Ses dosyası boş.")
    if len(audio_bytes) > 8 * 1024 * 1024:  # 8 MB üst sınır — kötüye kullanım koruması
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Ses dosyası çok büyük.")
    try:
        text = get_stt_provider().transcribe(audio_bytes, language=language)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=f"Ses tanıma hatası: {exc}") from exc
    return {"text": text}
