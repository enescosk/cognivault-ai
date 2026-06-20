from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from urllib.parse import parse_qs

from app.core.exceptions import ConflictError, NotFoundError, PermissionError, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.observability import webhook_inbound_total
from app.models import (
    Clinic,
    ClinicBranch,
    ClinicChannel,
    ClinicConversation,
    ClinicConversationStatus,
    ClinicIntent,
    ClinicMembership,
    ClinicMessage,
    ClinicMessageSender,
    ClinicPatient,
    ClinicUserRole,
    ClinicalAppointment,
    ClinicalAppointmentProcedure,
    ClinicalAppointmentStatus,
    ClinicalProcedureStatus,
    ConsentRecord,
    ConsentType,
    Doctor,
    FrustrationLog,
    InboundEvent,
    PreIntake,
    RoleName,
    ShadowReview,
    ShadowReviewStatus,
    User,
)
from app.services.agents import AgentType, DecisionRisk, build_decision, record_agent_decision
from app.services.clinical_ai_service import (
    analyze_sentiment,
    assess_hallucination_risk,
    derive_consent_signal,
    detect_frustration,
    detect_language,
    detect_multi_intents,
    generate_clinical_reply,
)
from app.services.clinical_feedback_service import update_shadow_review
from app.services.clinical_appointment_service import (
    create_clinical_appointment_from_conversation,
    create_manual_clinical_appointment,
    recent_clinical_appointments,
    resolve_appointment_doctor,
    set_clinical_appointment_status,
    upcoming_clinical_appointments,
    update_appointment_clinical_details,
)
from app.services.clinical_pre_intake_service import (
    create_pre_intake,
    get_pre_intake,
    list_pre_intakes,
    update_pre_intake,
)


# KVKK Md. 10 — Aydınlatma metni sürümü. Metin değişirse versiyon yükseltilmeli.
KVKK_NOTICE_VERSION = "v1.0.0"

# KVKK retention politikası — hasta verisi varsayılan 10 yıl saklanır.
# T.C. Sağlık Bakanlığı yönetmeliği ile uyumlu (Md. 7).
RETENTION_PERIOD_YEARS = 10

# KVKK Md. 10 aydınlatma metni — {clinic_name} ve {clinic_email} runtime'da doldurulur.
KVKK_NOTICE_TEMPLATE_TR = (
    "Merhaba, ben {clinic_name} AI asistanıyım. Görüşmeniz sırasında ad-soyad, "
    "telefon numaranız ve sağlık şikayetiniz gibi kişisel verileriniz yalnızca "
    "randevu oluşturma amacıyla işlenecektir. Verileriniz Türkiye sınırları içinde "
    "saklanmakta olup üçüncü taraflarla paylaşılmamaktadır. KVKK kapsamındaki "
    "haklarınız için {clinic_email} adresine yazabilirsiniz. Açık rıza gerektiren "
    "bir işlem olursa devam etmeden önce ayrıca onayınız istenecektir."
)


def _build_kvkk_notice_text(clinic: Clinic) -> str:
    """Klinik bağlamına göre KVKK aydınlatma metnini oluşturur."""
    settings = clinic.settings_json or {}
    clinic_email = (
        settings.get("kvkk_contact_email")
        or settings.get("contact_email")
        or f"kvkk@{clinic.slug}.local"
    )
    return KVKK_NOTICE_TEMPLATE_TR.format(
        clinic_name=clinic.name,
        clinic_email=clinic_email,
    )


@dataclass(frozen=True)
class IncomingClinicalMessage:
    from_phone: str
    body: str
    channel: ClinicChannel = ClinicChannel.WHATSAPP
    patient_name: str | None = None
    external_message_id: str | None = None
    external_thread_id: str | None = None
    conversation_id: int | None = None
    requested_persona_id: str | None = None
    raw_payload: dict | None = None


@dataclass(frozen=True)
class IngestionResult:
    clinic: Clinic
    patient: ClinicPatient
    conversation: ClinicConversation
    message: ClinicMessage
    action: str
    reply: str | None = None
    shadow_review: ShadowReview | None = None


def normalize_phone(value: str) -> str:
    phone = value.strip()
    if phone.startswith("whatsapp:"):
        phone = phone.removeprefix("whatsapp:")
    if phone.startswith("client:"):
        phone = phone.removeprefix("client:")
    return phone.replace(" ", "")


def parse_twilio_form(body: bytes) -> IncomingClinicalMessage:
    parsed = parse_qs(body.decode("utf-8"))
    from_phone = parsed.get("From", [""])[0]
    message_body = parsed.get("Body", [""])[0]
    profile_name = parsed.get("ProfileName", [None])[0]
    message_sid = parsed.get("MessageSid", [None])[0]
    if not from_phone or not message_body:
        raise ValidationError("Missing Twilio WhatsApp fields")
    return IncomingClinicalMessage(
        from_phone=normalize_phone(from_phone),
        body=message_body.strip(),
        channel=ClinicChannel.WHATSAPP,
        patient_name=profile_name,
        external_message_id=message_sid,
        external_thread_id=normalize_phone(from_phone),
        raw_payload={key: values[0] if values else None for key, values in parsed.items()},
    )


def parse_meta_payload(payload: dict) -> list[IncomingClinicalMessage]:
    messages: list[IncomingClinicalMessage] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            contacts = {item.get("wa_id"): item.get("profile", {}).get("name") for item in value.get("contacts", [])}
            for item in value.get("messages", []):
                text = item.get("text", {}).get("body")
                from_phone = item.get("from")
                if not from_phone or not text:
                    continue
                messages.append(
                    IncomingClinicalMessage(
                        from_phone=normalize_phone(from_phone),
                        body=text.strip(),
                        channel=ClinicChannel.WHATSAPP,
                        patient_name=contacts.get(from_phone),
                        external_message_id=item.get("id"),
                        external_thread_id=normalize_phone(from_phone),
                        raw_payload=item,
                    )
                )
    return messages


def ensure_default_clinic(db: Session) -> Clinic:
    settings = get_settings()
    clinic = db.scalars(select(Clinic).where(Clinic.slug == settings.clinical_default_clinic_slug)).first()
    if clinic is not None:
        return clinic

    # Patient page için varsayılan branding + KVKK aydınlatma metni.
    # Bunlar `settings_json` üstünden okunduğu için yeni tabloya gerek yok.
    _default_kvkk_body = (
        "Demo Klinik AI Resepsiyonu — KVKK Aydınlatma Metni v1.\n\n"
        "1. Veri Sorumlusu: Demo Klinik.\n"
        "2. İşlenen kişisel veriler: ad-soyad, telefon, sağlık şikayeti metni.\n"
        "3. Amaç: Randevu yönetimi, hastayla iletişim, hizmet kalitesi.\n"
        "4. Hukuki sebep: KVKK m.5/2-c (sözleşmenin kurulması) + m.6/3 (özel "
        "nitelikli sağlık verisi için açık rıza).\n"
        "5. Yurt dışı aktarımı: Sistem yerel sunucularda işlenir; ek olarak "
        "WhatsApp veya telefon kanalı kullanılırsa transit aracıları için "
        "ayrı m.9 onayınız sorulur.\n"
        "6. Saklama süresi: Konuşma kayıtları 90 gün anonimleştirilir, 1 yıl "
        "sonunda silinir. Randevu kaydı Sağlık Bakanlığı yönetmeliklerine "
        "tabidir.\n"
        "7. Haklarınız: 6698 sayılı Kanun m.11 kapsamındaki tüm haklara "
        "sahipsiniz (bilgi talebi, düzeltme, silme, itiraz). "
        "kvkk@demoklinik.com adresinden ulaşabilirsiniz.\n"
    )
    import hashlib as _hashlib

    _default_kvkk_hash = _hashlib.sha256(_default_kvkk_body.encode("utf-8")).hexdigest()

    clinic = Clinic(
        name="Demo Klinik",
        slug=settings.clinical_default_clinic_slug,
        default_language="tr",
        ai_auto_reply_threshold=settings.clinical_auto_reply_threshold,
        shadow_review_threshold=settings.clinical_shadow_threshold,
        settings_json={
            "pricing_policy": "Prices vary by department and clinician.",
            "kvkk_note": "Demo data only; production requires Turkish hosting and DPA review.",
            "branding": {
                "headline": "Demo Klinik AI Resepsiyonu",
                "sub_headline": "Saniyeler içinde KVKK onayı verip AI asistanımızla randevu alın.",
                "logo_url": None,
                "primary_color": "#1f3b73",
                "accent_color": "#28c8a6",
                "contact_phone": "+90 212 000 00 00",
                "public_address": "Demo Cad. No:12, İstanbul",
                "services": [
                    "Genel Diş Hekimliği",
                    "Endodonti",
                    "Ortodonti",
                    "İmplantoloji",
                    "Estetik Diş Hekimliği",
                    "Dermatoloji",
                    "Medikal Estetik",
                ],
            },
            "kvkk_disclosures": [
                {
                    "version": "v1",
                    "headline": "Kişisel Verilerin İşlenmesi — Aydınlatma",
                    "body": _default_kvkk_body,
                    "body_hash": _default_kvkk_hash,
                    "is_active": True,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            ],
        },
    )
    db.add(clinic)
    db.flush()
    db.add(
        ClinicBranch(
            clinic_id=clinic.id,
            name="Merkez Sube",
            address="Istanbul",
            phone="+90 212 000 00 00",
            working_hours_json={"weekdays": "09:00-18:00", "saturday": "10:00-14:00"},
        )
    )
    db.commit()
    db.refresh(clinic)
    return clinic


def ensure_clinic_access(db: Session, current_user: User, *, allow_clinician: bool = False) -> Clinic:
    if current_user.role.name not in {RoleName.OPERATOR, RoleName.ADMIN}:
        raise PermissionError("Clinical dashboard requires operator access")

    clinic: Clinic | None = None
    if current_user.organization_id is not None:
        # Tenant-aware path: scope the visible clinic to the user's organisation.
        clinic = db.scalars(
            select(Clinic)
            .where(Clinic.organization_id == current_user.organization_id)
            .order_by(Clinic.id)
        ).first()
    if clinic is None:
        # Legacy single-tenant fallback for users that pre-date the org backfill.
        clinic = ensure_default_clinic(db)

    membership = db.scalars(
        select(ClinicMembership).where(
            ClinicMembership.clinic_id == clinic.id,
            ClinicMembership.user_id == current_user.id,
        )
    ).first()
    if membership is None:
        linked_doctor = db.scalars(
            select(Doctor).where(Doctor.clinic_id == clinic.id, Doctor.user_id == current_user.id)
        ).first()
        db.add(
            ClinicMembership(
                clinic_id=clinic.id,
                user_id=current_user.id,
                role=(
                    ClinicUserRole.OWNER
                    if current_user.role.name == RoleName.ADMIN
                    else ClinicUserRole.CLINICIAN
                    if linked_doctor is not None
                    else ClinicUserRole.OPERATOR
                ),
            )
        )
        db.commit()
        membership = db.scalars(
            select(ClinicMembership).where(
                ClinicMembership.clinic_id == clinic.id,
                ClinicMembership.user_id == current_user.id,
            )
        ).first()
    if membership is not None and membership.role == ClinicUserRole.CLINICIAN and not allow_clinician:
        raise PermissionError("Clinician account is limited to its assigned review queue")
    return clinic


def get_clinician_doctor(db: Session, clinic: Clinic, current_user: User) -> Doctor | None:
    membership = db.scalars(
        select(ClinicMembership).where(
            ClinicMembership.clinic_id == clinic.id,
            ClinicMembership.user_id == current_user.id,
        )
    ).first()
    if membership is None or membership.role != ClinicUserRole.CLINICIAN:
        return None
    doctor = db.scalars(
        select(Doctor).where(
            Doctor.clinic_id == clinic.id,
            Doctor.user_id == current_user.id,
            Doctor.is_active.is_(True),
        )
    ).first()
    if doctor is None:
        raise PermissionError("Clinician account is not linked to an active doctor record")
    return doctor


def _assign_review_doctor(db: Session, clinic: Clinic, data: dict | None) -> Doctor | None:
    linked_doctors = list(
        db.scalars(
            select(Doctor)
            .where(Doctor.clinic_id == clinic.id, Doctor.user_id.is_not(None), Doctor.is_active.is_(True))
            .order_by(Doctor.id)
        )
    )
    if not linked_doctors:
        return None
    intake = (data or {}).get("intake")
    specialty = intake.get("specialty") if isinstance(intake, dict) else None
    if isinstance(specialty, str):
        normalized = specialty.strip().casefold()
        for doctor in linked_doctors:
            if doctor.specialty.strip().casefold() == normalized:
                return doctor
    return linked_doctors[0]



def _find_or_create_patient(db: Session, clinic: Clinic, incoming: IncomingClinicalMessage) -> ClinicPatient:
    phone = normalize_phone(incoming.from_phone)
    patient = db.scalars(select(ClinicPatient).where(ClinicPatient.clinic_id == clinic.id, ClinicPatient.phone == phone)).first()
    if patient is not None:
        if incoming.patient_name and not patient.full_name:
            patient.full_name = incoming.patient_name
            db.add(patient)
            db.commit()
            db.refresh(patient)
        return patient

    language = detect_language(incoming.body, clinic.default_language)
    patient = ClinicPatient(
        clinic_id=clinic.id,
        full_name=incoming.patient_name,
        phone=phone,
        language=language,
        source=incoming.channel,
        external_ref=phone,
        metadata_json={},
    )
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return patient


def _find_or_create_conversation(db: Session, clinic: Clinic, patient: ClinicPatient, incoming: IncomingClinicalMessage) -> ClinicConversation:
    if incoming.conversation_id is not None:
        conversation = db.scalars(
            select(ClinicConversation).where(
                ClinicConversation.id == incoming.conversation_id,
                ClinicConversation.clinic_id == clinic.id,
                ClinicConversation.patient_id == patient.id,
                ClinicConversation.channel == incoming.channel,
            )
        ).first()
        if conversation is None:
            raise ValidationError("Conversation scope mismatch")
        return conversation

    conversation = db.scalars(
        select(ClinicConversation)
        .where(
            ClinicConversation.clinic_id == clinic.id,
            ClinicConversation.patient_id == patient.id,
            ClinicConversation.channel == incoming.channel,
            ClinicConversation.status.in_(
                [
                    ClinicConversationStatus.ACTIVE,
                    ClinicConversationStatus.WAITING_HUMAN,
                    ClinicConversationStatus.APPOINTMENT_PENDING,
                ]
            ),
        )
        .order_by(ClinicConversation.updated_at.desc())
    ).first()
    if conversation is not None:
        return conversation

    now = datetime.now(timezone.utc)
    conversation = ClinicConversation(
        clinic_id=clinic.id,
        patient_id=patient.id,
        channel=incoming.channel,
        language=patient.language,
        external_thread_id=incoming.external_thread_id or patient.phone,
        metadata_json={},
        # KVKK retention — 10 yıl sonra anonymization sürecine girer
        data_expires_at=now + timedelta(days=365 * RETENTION_PERIOD_YEARS),
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)

    # Hasta ilk kez yazıyor — KVKK Md. 10 aydınlatma yükümlülüğünü yerine getir.
    # Bildirim ile açık rızayı karıştırmamak için kayıt pending/granted=False açılır.
    _emit_kvkk_notice_and_pending_consent(db, clinic, patient, conversation)

    # Hasta için ilk kayıt anında data_expires_at'i de set et (varsa override etme).
    if patient.data_expires_at is None:
        patient.data_expires_at = now + timedelta(days=365 * RETENTION_PERIOD_YEARS)
        db.commit()

    return conversation


def _emit_kvkk_notice_and_pending_consent(
    db: Session,
    clinic: Clinic,
    patient: ClinicPatient,
    conversation: ClinicConversation,
) -> None:
    """KVKK Md. 10 aydınlatmasını yaz ve henüz verilmemiş rızayı kaydet.

    Hasta WhatsApp/telefon/web üzerinden ilk kez geldiğinde tetiklenir. Mesaj
    `sender=system` ile kaydedilir ki gerçek hasta/asistan dialogundan ayırt edilebilsin.
    Salt görüşmeye devam etmek açık rıza sayılmaz. Web/DTMF gibi doğrulanabilir bir
    aksiyon ayrı endpoint üzerinden bu kaydı granted hale getirmelidir.
    """
    notice_text = _build_kvkk_notice_text(clinic)
    system_message = ClinicMessage(
        clinic_id=clinic.id,
        conversation_id=conversation.id,
        sender=ClinicMessageSender.SYSTEM,
        content=notice_text,
        language=patient.language,
        intent=None,
        metadata_json={
            "kvkk_notice": True,
            "consent_text_version": KVKK_NOTICE_VERSION,
        },
    )
    db.add(system_message)

    consent_row = ConsentRecord(
        clinic_id=clinic.id,
        patient_id=patient.id,
        conversation_id=conversation.id,
        consent_type=ConsentType.DATA_PROCESSING,
        granted=False,
        channel=conversation.channel,
        consent_text_version=KVKK_NOTICE_VERSION,
    )
    db.add(consent_row)
    db.commit()


def _provider_from_channel(channel: ClinicChannel) -> str:
    if channel == ClinicChannel.WHATSAPP:
        return "whatsapp"
    if channel == ClinicChannel.PHONE:
        return "voice"
    return channel.value


def _existing_inbound_message(
    db: Session, clinic: Clinic, provider: str, external_id: str
) -> ClinicMessage | None:
    return db.scalars(
        select(ClinicMessage)
        .where(
            ClinicMessage.clinic_id == clinic.id,
            ClinicMessage.external_message_id == external_id,
        )
        .order_by(ClinicMessage.created_at.desc())
    ).first()


def _has_active_cross_border_consent(
    db: Session,
    clinic: Clinic,
    patient: ClinicPatient,
    conversation: ClinicConversation,
) -> bool:
    consent = db.scalars(
        select(ConsentRecord)
        .where(
            ConsentRecord.clinic_id == clinic.id,
            ConsentRecord.patient_id == patient.id,
            ConsentRecord.conversation_id == conversation.id,
            ConsentRecord.consent_type == ConsentType.CROSS_BORDER_TRANSFER,
            ConsentRecord.granted.is_(True),
            ConsentRecord.withdrawn_at.is_(None),
        )
        .order_by(ConsentRecord.granted_at.desc())
    ).first()
    return consent is not None


def ingest_clinical_message(db: Session, incoming: IncomingClinicalMessage, clinic: Clinic | None = None, use_ai: bool = True) -> IngestionResult:
    clinic = clinic or ensure_default_clinic(db)

    if incoming.external_message_id:
        provider = _provider_from_channel(incoming.channel)
        existing_event = db.scalars(
            select(InboundEvent).where(
                InboundEvent.provider == provider,
                InboundEvent.external_id == incoming.external_message_id,
            )
        ).first()
        if existing_event is not None:
            existing_message = _existing_inbound_message(
                db, clinic, provider, incoming.external_message_id
            )
            if existing_message is not None:
                conversation = db.get(ClinicConversation, existing_message.conversation_id)
                patient = db.get(ClinicPatient, conversation.patient_id) if conversation else None
                if conversation is not None and patient is not None:
                    webhook_inbound_total.labels(provider, "duplicate").inc()
                    return IngestionResult(
                        clinic=clinic,
                        patient=patient,
                        conversation=conversation,
                        message=existing_message,
                        action="duplicate_ignored",
                        reply=None,
                        shadow_review=None,
                    )
        db.add(
            InboundEvent(
                clinic_id=clinic.id,
                provider=provider,
                external_id=incoming.external_message_id,
                payload_json={"channel": incoming.channel.value, "from_phone": incoming.from_phone},
            )
        )
        db.commit()
        webhook_inbound_total.labels(provider, "accepted").inc()

    patient = _find_or_create_patient(db, clinic, incoming)
    conversation = _find_or_create_conversation(db, clinic, patient, incoming)
    language = detect_language(incoming.body, patient.language or clinic.default_language)

    patient.language = language
    conversation.language = language
    conversation.last_patient_message_at = datetime.now(timezone.utc)
    conversation.status = ClinicConversationStatus.ACTIVE
    db.add(patient)
    db.add(conversation)
    db.commit()

    # Faz 2 — Hasta mesajı için research-driven sinyaller (sentiment, multi-intent).
    # Bunlar AI cevabından önce hesaplanır ki frustrated patient akışını AI'a beslemeden
    # de loglayabilelim ve hasta mesajının kendi metadata'sında saklayabilelim.
    patient_sentiment = analyze_sentiment(incoming.body)
    patient_is_frustrated = detect_frustration(incoming.body)

    message = ClinicMessage(
        clinic_id=clinic.id,
        conversation_id=conversation.id,
        sender=ClinicMessageSender.PATIENT,
        content=incoming.body,
        language=language,
        external_message_id=incoming.external_message_id,
        metadata_json={
            "raw_payload": incoming.raw_payload or {},
            "source": incoming.channel.value,
            # UI'da SentimentStrip'in beslendiği alan (Bölüm F#9)
            "sentiment_score": patient_sentiment,
            "is_frustrated": patient_is_frustrated,
        },
    )
    db.add(message)
    db.commit()
    db.refresh(message)

    ai_result = generate_clinical_reply(
        clinic,
        incoming.body,
        language,
        incoming.requested_persona_id,
        use_ai=use_ai,
        previous_intent=conversation.intent,
        external_ai_consent=_has_active_cross_border_consent(db, clinic, patient, conversation),
    )

    # Multi-intent ve consent sinyallerini AI çıktısı sonrası hesapla.
    # Primary intent ai_result.intent'ten geliyor; secondary'leri ondan çıkarıyoruz.
    secondary_intents = detect_multi_intents(incoming.body, ai_result.intent)
    governance_dict = (ai_result.data or {}).get("privacy_guardrail") or {}
    consent_signal = derive_consent_signal(governance_dict)

    # Patient message metadata'sını intent listesi ve consent ile zenginleştir.
    # JSON mutation: SQLAlchemy MutableDict bunu izler ama emin olmak için explicit set.
    enriched_patient_metadata = {
        **(message.metadata_json or {}),
        "intents": [ai_result.intent.value, *secondary_intents] if secondary_intents else [ai_result.intent.value],
        "kvkk_consent": consent_signal,
    }
    message.metadata_json = enriched_patient_metadata
    db.add(message)

    conversation.intent = ai_result.intent
    conversation.confidence_score = ai_result.confidence
    conversation.metadata_json = {
        **(conversation.metadata_json or {}),
        "last_persona_id": ai_result.persona_id,
        "last_persona_name": ai_result.persona_name,
        "last_voice": ai_result.voice,
        "last_channel": incoming.channel.value,
        # Bölüm C — KVKK consent durumu sohbet seviyesinde
        "kvkk_consent": consent_signal,
        # Son sentiment skoru — trajectory ileri analiz için
        "last_patient_sentiment": patient_sentiment,
    }

    if detect_frustration(incoming.body):
        db.add(
            FrustrationLog(
                clinic_id=clinic.id,
                conversation_id=conversation.id,
                trigger="patient_language",
                severity=2,
                message_excerpt=incoming.body[:500],
                metadata_json={"source_message_id": message.id, "channel": incoming.channel.value},
            )
        )

    needs_shadow = ai_result.requires_human_review or ai_result.confidence < clinic.ai_auto_reply_threshold
    if needs_shadow:
        conversation.status = ClinicConversationStatus.WAITING_HUMAN
        assigned_doctor = _assign_review_doctor(db, clinic, ai_result.data)
        review = ShadowReview(
            clinic_id=clinic.id,
            conversation_id=conversation.id,
            patient_message_id=message.id,
            assigned_doctor_id=assigned_doctor.id if assigned_doctor else None,
            draft_reply=ai_result.reply,
            intent=ai_result.intent,
            confidence_score=ai_result.confidence,
            risk_reason=ai_result.risk_reason or "requires_human_review",
            metadata_json={
                "action": ai_result.action,
                "data": ai_result.data or {},
                "persona_id": ai_result.persona_id,
                "persona_name": ai_result.persona_name,
                "voice": ai_result.voice,
                "channel": incoming.channel.value,
                "doctor_inbox": True,
            },
        )
        db.add(conversation)
        db.add(review)
        db.commit()
        db.refresh(conversation)
        db.refresh(review)
        record_agent_decision(
            db,
            build_decision(
                agent_type=AgentType.ROUTING,
                intent=ai_result.intent.value if hasattr(ai_result.intent, "value") else str(ai_result.intent),
                confidence=ai_result.confidence,
                risk=DecisionRisk.HIGH,
                requires_human=True,
                action="shadow_review",
                reason=ai_result.risk_reason or "requires_human_review",
                organization_id=clinic.organization_id,
                payload={
                    "channel": incoming.channel.value,
                    "shadow_review_id": review.id,
                    "persona_id": ai_result.persona_id,
                },
            ),
            clinic_id=clinic.id,
            conversation_id=conversation.id,
        )
        return IngestionResult(
            clinic=clinic,
            patient=patient,
            conversation=conversation,
            message=message,
            action="shadow_review",
            shadow_review=review,
        )

    # Faz 2 — Asistan mesajı için research-driven sinyaller.
    # hallucination_risk: AI cevabında somut saat var ama slot service müsait slot dönmediyse.
    # emergency_routed: medical_emergency intent'inde AI cevabı 112'ye yönlendirdiyse.
    slot_decision = (ai_result.data or {}).get("slot_decision") or {}
    hallucination_risk, hallucination_reason = assess_hallucination_risk(
        ai_result.reply, ai_result.intent, slot_decision
    )
    is_emergency_intent = ai_result.intent == ClinicIntent.MEDICAL_EMERGENCY
    routed_to_112 = is_emergency_intent and bool(re.search(r"\b112\b|acil servis", ai_result.reply.lower()))

    assistant_message = ClinicMessage(
        clinic_id=clinic.id,
        conversation_id=conversation.id,
        sender=ClinicMessageSender.ASSISTANT,
        content=ai_result.reply,
        language=language,
        intent=ai_result.intent,
        confidence_score=ai_result.confidence,
        metadata_json={
            "action": ai_result.action,
            "delivery": "simulated",
            "data": ai_result.data or {},
            "persona_id": ai_result.persona_id,
            "persona_name": ai_result.persona_name,
            "voice": ai_result.voice,
            "channel": incoming.channel.value,
            # Bölüm B#1 — UI'da kırmızı kenar + ⚠ tetikleyen alan
            "hallucination_risk": hallucination_risk,
            "hallucination_reason": hallucination_reason,
            # Bölüm A6 — EmergencyBanner'ın "112 yönlendirildi mi" rozetinin beslendiği alan
            "emergency_intent": is_emergency_intent,
            "emergency_routed": routed_to_112,
            # Patient message ile aynı consent imzası — audit/forensic için kopyalı
            "kvkk_consent": consent_signal,
        },
    )
    db.add(assistant_message)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    record_agent_decision(
        db,
        build_decision(
            agent_type=AgentType.SUPPORT,
            intent=ai_result.intent.value if hasattr(ai_result.intent, "value") else str(ai_result.intent),
            confidence=ai_result.confidence,
            risk=DecisionRisk.LOW,
            requires_human=False,
            action=ai_result.action or "auto_reply",
            reason="confidence_above_threshold",
            organization_id=clinic.organization_id,
            payload={
                "channel": incoming.channel.value,
                "assistant_message_id": assistant_message.id,
                "persona_id": ai_result.persona_id,
            },
        ),
        clinic_id=clinic.id,
        conversation_id=conversation.id,
    )
    return IngestionResult(
        clinic=clinic,
        patient=patient,
        conversation=conversation,
        message=message,
        action="auto_reply",
        reply=ai_result.reply,
    )


def list_clinical_conversations(db: Session, clinic: Clinic, limit: int = 30) -> list[ClinicConversation]:
    return list(
        db.scalars(
            select(ClinicConversation)
            .options(selectinload(ClinicConversation.patient), selectinload(ClinicConversation.messages))
            .where(ClinicConversation.clinic_id == clinic.id)
            .order_by(ClinicConversation.updated_at.desc())
            .limit(limit)
        )
    )


def get_clinical_conversation(db: Session, clinic: Clinic, conversation_id: int) -> ClinicConversation:
    conversation = db.scalars(
        select(ClinicConversation)
        .options(selectinload(ClinicConversation.patient), selectinload(ClinicConversation.messages))
        .where(ClinicConversation.clinic_id == clinic.id, ClinicConversation.id == conversation_id)
    ).first()
    if conversation is None:
        raise NotFoundError("Clinical conversation not found")
    return conversation


def list_shadow_reviews(
    db: Session,
    clinic: Clinic,
    status_value: ShadowReviewStatus | None = ShadowReviewStatus.PENDING,
    *,
    doctor_id: int | None = None,
) -> list[ShadowReview]:
    query = select(ShadowReview).where(ShadowReview.clinic_id == clinic.id).order_by(ShadowReview.created_at.desc())
    if status_value is not None:
        query = query.where(ShadowReview.status == status_value)
    if doctor_id is not None:
        query = query.where(ShadowReview.assigned_doctor_id == doctor_id)
    return list(db.scalars(query))


def list_doctor_inbox(
    db: Session,
    clinic: Clinic,
    limit: int = 30,
    *,
    doctor_id: int | None = None,
) -> list[ClinicConversation]:
    query = (
        select(ClinicConversation)
        .options(selectinload(ClinicConversation.patient), selectinload(ClinicConversation.messages))
        .where(
            ClinicConversation.clinic_id == clinic.id,
            ClinicConversation.status.in_(
                [
                    ClinicConversationStatus.WAITING_HUMAN,
                    ClinicConversationStatus.APPOINTMENT_PENDING,
                ]
            ),
        )
    )
    if doctor_id is not None:
        query = query.join(ShadowReview, ShadowReview.conversation_id == ClinicConversation.id).where(
            ShadowReview.assigned_doctor_id == doctor_id
        ).distinct()
    return list(db.scalars(query.order_by(ClinicConversation.updated_at.desc()).limit(limit)))



def clinical_metrics(db: Session, clinic: Clinic, *, doctor_id: int | None = None) -> dict:
    today_start = datetime.combine(datetime.now(timezone.utc).date(), time.min, tzinfo=timezone.utc)
    total_conversations = db.scalar(select(func.count(ClinicConversation.id)).where(ClinicConversation.clinic_id == clinic.id)) or 0
    conversations_today = (
        db.scalar(
            select(func.count(ClinicConversation.id)).where(
                ClinicConversation.clinic_id == clinic.id,
                ClinicConversation.created_at >= today_start,
            )
        )
        or 0
    )
    pending_query = select(func.count(ShadowReview.id)).where(
        ShadowReview.clinic_id == clinic.id,
        ShadowReview.status == ShadowReviewStatus.PENDING,
    )
    if doctor_id is not None:
        pending_query = pending_query.where(ShadowReview.assigned_doctor_id == doctor_id)
    pending_shadow = db.scalar(pending_query) or 0
    if doctor_id is not None:
        doctor_inbox_count = pending_shadow
    else:
        doctor_inbox_count = (
            db.scalar(
                select(func.count(ClinicConversation.id)).where(
                    ClinicConversation.clinic_id == clinic.id,
                    ClinicConversation.status.in_(
                        [ClinicConversationStatus.WAITING_HUMAN, ClinicConversationStatus.APPOINTMENT_PENDING]
                    ),
                )
            )
            or 0
        )
    phone_calls_today = (
        db.scalar(
            select(func.count(ClinicConversation.id)).where(
                ClinicConversation.clinic_id == clinic.id,
                ClinicConversation.channel == ClinicChannel.PHONE,
                ClinicConversation.created_at >= today_start,
            )
        )
        or 0
    )
    assistant_messages = (
        db.scalar(
            select(func.count(ClinicMessage.id)).where(
                ClinicMessage.clinic_id == clinic.id,
                ClinicMessage.sender == ClinicMessageSender.ASSISTANT,
            )
        )
        or 0
    )
    patient_messages = (
        db.scalar(
            select(func.count(ClinicMessage.id)).where(
                ClinicMessage.clinic_id == clinic.id,
                ClinicMessage.sender == ClinicMessageSender.PATIENT,
            )
        )
        or 0
    )
    appointments_pending = (
        db.scalar(
            select(func.count(ClinicalAppointment.id)).where(
                ClinicalAppointment.clinic_id == clinic.id,
                ClinicalAppointment.status == ClinicalAppointmentStatus.PENDING,
            )
        )
        or 0
    )
    reminders_due = len(upcoming_clinical_appointments(db, clinic, within_minutes=120))
    frustration_events = db.scalar(select(func.count(FrustrationLog.id)).where(FrustrationLog.clinic_id == clinic.id)) or 0
    return {
        "clinic_name": clinic.name,
        "conversations_today": conversations_today,
        "total_conversations": total_conversations,
        "pending_shadow_reviews": pending_shadow,
        "doctor_inbox_count": doctor_inbox_count,
        "phone_calls_today": phone_calls_today,
        "auto_reply_rate": round(assistant_messages / patient_messages, 2) if patient_messages else 0.0,
        "appointments_pending": appointments_pending,
        "reminders_due": reminders_due,
        "frustration_events": frustration_events,
    }
