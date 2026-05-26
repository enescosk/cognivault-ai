from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.config import get_settings
from app.models import Clinic, ClinicIntent


IDENTIFIER_PATTERNS = [
    re.compile(r"\b\d{11}\b"),
    re.compile(r"\b(?:\d[ -]?){13,19}\b"),
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    re.compile(r"\+?\d[\d\s()\-]{7,}\d"),
]

HEALTH_DATA_INTENTS = {
    ClinicIntent.BOOK_APPOINTMENT,
    ClinicIntent.RESCHEDULE_APPOINTMENT,
    ClinicIntent.CANCEL_APPOINTMENT,
    ClinicIntent.MEDICAL_EMERGENCY,
    ClinicIntent.GENERAL_QUESTION,
}

FINANCIAL_DATA_INTENTS = {ClinicIntent.ASK_PRICE, ClinicIntent.ASK_INSURANCE}


@dataclass(frozen=True)
class GovernanceContext:
    data_classes: list[str]
    sensitivity: str
    data_residency_mode: str
    external_transfer_allowed: bool
    required_controls: list[str]
    consent_required_before: list[str]
    human_review_reasons: list[str]
    redacted_preview: str

    @property
    def auto_send_allowed(self) -> bool:
        return not self.human_review_reasons

    def as_dict(self) -> dict:
        return {
            "data_classes": self.data_classes,
            "sensitivity": self.sensitivity,
            "data_residency_mode": self.data_residency_mode,
            "external_transfer_allowed": self.external_transfer_allowed,
            "required_controls": self.required_controls,
            "consent_required_before": self.consent_required_before,
            "human_review_reasons": self.human_review_reasons,
            "auto_send_allowed": self.auto_send_allowed,
            "redacted_preview": self.redacted_preview,
        }


def redact_sensitive_text(text: str) -> str:
    redacted = text
    for pattern in IDENTIFIER_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted[:500]


def _detect_data_classes(text: str, intent: ClinicIntent) -> list[str]:
    normalized = text.lower()
    classes = {"contact_data"}
    if intent in HEALTH_DATA_INTENTS or any(term in normalized for term in ("diş", "dis", "ağrı", "agri", "implant", "kanama")):
        classes.add("special_category_health_data")
    if intent in FINANCIAL_DATA_INTENTS or any(term in normalized for term in ("sigorta", "sgk", "provizyon", "kart")):
        classes.add("financial_or_insurance_data")
    if re.search(r"\b\d{11}\b", text):
        classes.add("national_identifier")
    if "ses" in normalized or "arama" in normalized:
        classes.add("voice_interaction_metadata")
    return sorted(classes)


def build_governance_context(clinic: Clinic, text: str, intent: ClinicIntent, language: str) -> GovernanceContext:
    settings = clinic.settings_json or {}
    data_residency_mode = settings.get("data_residency_mode", "tr_local_first")
    external_transfer_allowed = bool(settings.get("allow_cross_border_processors", False))
    data_classes = _detect_data_classes(text, intent)

    controls = [
        "explicit_notice",
        "purpose_limitation",
        "data_minimization",
        "role_based_access",
        "audit_logging",
        "retention_policy",
        "doctor_approval_for_medical_risk",
        "no_diagnosis_or_treatment_instruction",
    ]
    consent_before = ["voice_recording_storage", "insurance_or_identity_lookup"]
    human_review_reasons: list[str] = []

    if "special_category_health_data" in data_classes:
        controls.append("special_category_data_safeguards")
    if not external_transfer_allowed:
        controls.append("block_cross_border_ai_processors")
    else:
        consent_before.append("cross_border_ai_processing")

    if intent == ClinicIntent.MEDICAL_EMERGENCY:
        human_review_reasons.append("medical_emergency_requires_human_escalation")
    if intent == ClinicIntent.ASK_INSURANCE:
        human_review_reasons.append("insurance_verification_requires_explicit_consent")
    if "national_identifier" in data_classes:
        human_review_reasons.append("national_identifier_requires_operator_review")
    if data_residency_mode == "tr_local_first" and external_transfer_allowed:
        human_review_reasons.append("cross_border_processor_enabled_in_local_first_mode")

    sensitivity = "standard"
    if "special_category_health_data" in data_classes:
        sensitivity = "special_category"
    if intent == ClinicIntent.MEDICAL_EMERGENCY:
        sensitivity = "urgent_special_category"

    return GovernanceContext(
        data_classes=data_classes,
        sensitivity=sensitivity,
        data_residency_mode=data_residency_mode,
        external_transfer_allowed=external_transfer_allowed,
        required_controls=controls,
        consent_required_before=consent_before,
        human_review_reasons=human_review_reasons,
        redacted_preview=redact_sensitive_text(text),
    )


def build_compliance_profile(clinic: Clinic) -> dict:
    app_settings = get_settings()
    settings = clinic.settings_json or {}
    external_transfer_allowed = bool(settings.get("allow_cross_border_processors", False))
    return {
        "clinic_id": clinic.id,
        "clinic_name": clinic.name,
        "data_residency_default": settings.get("data_residency_mode", "tr_local_first"),
        "external_transfer_allowed": external_transfer_allowed,
        "processor_inventory": [
            {
                "id": "openai",
                "purpose": "general_chat_or_voice_when_enabled",
                "configured": bool(app_settings.openai_api_key),
                "allowed_for_clinical": bool(app_settings.clinical_external_ai_allowed and external_transfer_allowed),
                "clinical_default": "blocked",
            },
            {
                "id": "anthropic",
                "purpose": "clinical_llm_draft_when_explicitly_enabled",
                "configured": bool(app_settings.anthropic_api_key),
                "allowed_for_clinical": bool(app_settings.clinical_ai_enabled and app_settings.clinical_external_ai_allowed and external_transfer_allowed),
                "clinical_default": "blocked",
            },
            {
                "id": "external_voice_stt_tts",
                "purpose": "speech_to_text_and_text_to_speech",
                "configured": bool(app_settings.openai_api_key),
                "allowed_for_clinical": bool(app_settings.voice_external_enabled and external_transfer_allowed),
                "clinical_default": "blocked",
            },
            {
                "id": "twilio_meta",
                "purpose": "telephony_and_whatsapp_transport",
                "configured": bool(app_settings.twilio_account_sid or app_settings.meta_access_token),
                "allowed_for_clinical": bool(external_transfer_allowed),
                "clinical_default": "transport_only_after_dpa_and_consent_review",
            },
        ],
        "production_modes": [
            {
                "id": "kvkk_local",
                "label": "KVKK local-first",
                "description": "ASR, LLM, TTS, audit log and database stay in Turkey or on-premise. Cross-border AI processors are blocked by default.",
            },
            {
                "id": "hybrid_explicit_consent",
                "label": "Hybrid with explicit consent",
                "description": "Foreign processors may be used only after explicit notice, consent capture, processor contract review and audit tagging.",
            },
        ],
        "mandatory_controls": [
            "explicit_notice",
            "purpose_limitation",
            "data_minimization",
            "special_category_data_safeguards",
            "role_based_access",
            "doctor_approval_for_medical_risk",
            "audit_logging",
            "retention_policy",
            "right_to_erasure_workflow",
            "processor_registry",
        ],
        "blocked_by_default": [
            "diagnosis",
            "treatment_instruction",
            "unapproved_insurance_lookup",
            "unconsented_voice_recording_storage",
            "cross_border_ai_processing_without_consent",
            "external_llm_for_special_category_health_data",
            "external_stt_tts_for_patient_voice_without_explicit_policy",
        ],
        "operator_review_triggers": [
            "medical_emergency",
            "priority_dental_symptom",
            "insurance_or_identity_lookup",
            "low_confidence_intent",
            "patient_frustration_detected",
            "national_identifier_detected",
        ],
        # KVKK Md. 7 — Saklama (Retention) Politikası
        # Hasta verisi varsayılan 10 yıl tutulur, sonra anonymization (`right_to_erasure`
        # iş akışı) tetiklenir. Süre dolan kayıtlar `data_expires_at` kolonu ile takip edilir.
        "retention_policy": {
            "default_period_years": 10,
            "anchor_field": "data_expires_at",
            "anchored_tables": ["clinic_patients", "clinic_conversations"],
            "post_expiry_action": "anonymize_via_right_to_erasure",
            "legal_basis": "T.C. Sağlık Bakanlığı Kişisel Sağlık Verileri Yönetmeliği Md. 7",
            "patient_initiated_erasure_endpoint": "DELETE /api/clinical/patients/{patient_id}/erasure",
        },
    }


def build_patent_dossier(clinic: Clinic) -> dict:
    return {
        "working_title": "KVKK-first multimodal dental AI receptionist with deterministic clinical governance and appointment write-back",
        "technical_field": "Healthcare call automation, speech AI, clinical workflow orchestration, privacy-preserving appointment systems.",
        "problem": (
            "Dental clinics lose calls and revenue while generic voice bots either over-collect health data, hallucinate medical guidance "
            "or cannot deterministically route Turkish colloquial dental complaints into safe appointment workflows."
        ),
        "solution_summary": (
            "A hybrid engine classifies Turkish patient speech, maps colloquial dental complaints to specialty routing, applies a deterministic "
            "KVKK governance layer, blocks unsafe automated actions, and prepares PMS write-back or doctor approval packets with redacted audit metadata."
        ),
        "candidate_independent_claims": [
            "A computer-implemented method that transforms real-time Turkish dental patient speech into a specialty-specific appointment workflow by combining semantic complaint routing with deterministic privacy and clinical-safety gates.",
            "A system that prevents automatic transmission of high-risk dental, emergency, insurance or identifier-bearing responses unless consent, local processing mode and human review constraints are satisfied.",
            "A clinical orchestration apparatus that generates doctor approval packets containing intent, confidence, data class, redacted transcript preview, routing reason and permitted next actions for PMS write-back.",
        ],
        "candidate_dependent_claims": [
            "The method of claim 1, wherein colloquial terms such as zonkluyor, dolgu düştü, diş eti kanıyor and çocuğumun dişi are mapped to Endodonti, Restoratif, Periodontoloji or Pedodonti routing classes.",
            "The method of claim 1, wherein the system switches between local-first and consented hybrid processor modes and records the selected mode in an audit trail.",
            "The method of claim 2, wherein insurance verification is blocked until explicit consent and operator review are recorded.",
            "The method of claim 3, wherein the approval packet includes a redacted preview that masks phone numbers, national identifiers, email addresses and card-like numbers.",
        ],
        "figures_to_prepare": [
            "Figure 1: Telephony, ASR, hybrid reasoning, governance gate, PMS write-back and TTS flow.",
            "Figure 2: KVKK local-first versus hybrid explicit-consent deployment modes.",
            "Figure 3: Doctor approval packet generation and audit logging sequence.",
        ],
        "evidence_to_preserve": [
            "Research notes and source list",
            "Conversation scenario tables",
            "Routing keyword taxonomy",
            "Governance metadata examples",
            "Screenshots of operator and landing UX",
            "Test results proving safety gates",
        ],
        "next_actions": [
            "Run novelty search with TÜRKPATENT, EPO Espacenet and Google Patents before public disclosure.",
            "Have a patent attorney convert this technical dossier into formal claims, description, abstract and drawings.",
            "Avoid publishing enabling implementation details before filing if the team wants maximum novelty protection.",
        ],
    }


def run_retention_cleanup(db: Session) -> dict[str, int]:
    """
    Executes the KVKK retention cleanup.
    - Anonymizes ClinicMessage rows older than 90 days.
    - Anonymizes ClinicPatient & ClinicConversation rows whose data_expires_at has passed.
    """
    from datetime import datetime, timezone, timedelta
    import hashlib
    from sqlalchemy import select
    from app.models import ClinicPatient, ClinicConversation, ClinicMessage, ShadowReview, AuditResultStatus
    from app.services.audit_service import log_action
    from app.core.config import get_settings

    now = datetime.now(timezone.utc)
    settings = get_settings()

    # 1. Anonymize ClinicMessage rows older than 90 days
    cutoff_90_days = now - timedelta(days=90)
    messages_to_clean = list(db.scalars(
        select(ClinicMessage).where(
            ClinicMessage.created_at <= cutoff_90_days,
            ClinicMessage.content != "[İçerik KVKK gereği otomatik silindi]"
        )
    ).all())

    erased_message_count = 0
    for msg in messages_to_clean:
        msg.content = "[İçerik KVKK gereği otomatik silindi]"
        msg.metadata_json = {**(msg.metadata_json or {}), "auto_erased": True}
        db.add(msg)
        erased_message_count += 1

    # 2. Anonymize expired ClinicPatient rows
    expired_patients = list(db.scalars(
        select(ClinicPatient).where(
            ClinicPatient.data_expires_at.is_not(None),
            ClinicPatient.data_expires_at <= now,
            ClinicPatient.full_name != "[SİLİNDİ]"
        )
    ).all())

    erased_patient_count = 0
    for patient in expired_patients:
        pepper = f"{settings.jwt_secret}:{patient.clinic_id}".encode()
        hashed_phone = hashlib.sha256(patient.phone.encode() + pepper).hexdigest()[:32]
        patient.full_name = "[SİLİNDİ]"
        patient.phone = f"erased:{hashed_phone}"
        patient.metadata_json = {}
        patient.external_ref = None
        db.add(patient)
        erased_patient_count += 1

    # 3. Anonymize expired ClinicConversation rows
    expired_convs = list(db.scalars(
        select(ClinicConversation).where(
            ClinicConversation.data_expires_at.is_not(None),
            ClinicConversation.data_expires_at <= now,
            ClinicConversation.status != "closed"
        )
    ).all())

    erased_conv_count = 0
    for conv in expired_convs:
        conv.metadata_json = {**(conv.metadata_json or {}), "auto_erased": True}
        # Also clean up shadow reviews associated with this conversation
        reviews = list(db.scalars(
            select(ShadowReview).where(ShadowReview.conversation_id == conv.id)
        ).all())
        for review in reviews:
            review.draft_reply = "[Silindi]"
            if review.final_reply:
                review.final_reply = "[Silindi]"
            db.add(review)
        db.add(conv)
        erased_conv_count += 1

    if erased_message_count > 0 or erased_patient_count > 0 or erased_conv_count > 0:
        db.commit()
        log_action(
            db,
            user_id=None,
            action_type="retention_cleanup",
            explanation=(
                f"KVKK otomatik veri saklama temizliği çalıştı: "
                f"{erased_message_count} mesaj, {erased_patient_count} hasta, "
                f"{erased_conv_count} konuşma temizlendi."
            ),
            result_status=AuditResultStatus.SUCCESS,
            details={
                "messages_erased": erased_message_count,
                "patients_erased": erased_patient_count,
                "conversations_erased": erased_conv_count,
            }
        )

    return {
        "messages_erased": erased_message_count,
        "patients_erased": erased_patient_count,
        "conversations_erased": erased_conv_count,
    }

