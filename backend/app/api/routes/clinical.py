from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from html import escape
from urllib.parse import parse_qs

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.core.config import get_settings
from app.core.webhook_security import (
    signature_required,
    verify_meta_signature,
    verify_twilio_signature,
)
from app.models import ClinicBranch, ClinicChannel, ClinicConversation, ClinicDoctor, ClinicDoctorSlot, ClinicPatient, ClinicalAppointment, ClinicalVoiceQARun, RoleName, ShadowReview, ShadowReviewStatus, User
from app.schemas.clinical import (
    ClinicalAppointmentCreateRequest,
    ClinicalAppointmentDetailsUpdate,
    ClinicalAppointmentResponse,
    ClinicalAppointmentRow,
    ClinicalAppointmentStatusUpdate,
    ClinicalManualAppointmentRequest,
    ClinicalComplianceProfileResponse,
    ClinicDoctorResponse,
    ClinicDoctorSlotResponse,
    ClinicalConversationDetail,
    ClinicalConversationSummary,
    ClinicalMessageResponse,
    ClinicalMetricsResponse,
    ClinicalOverviewResponse,
    ClinicalPilotMetricsResponse,
    ClinicalPilotWeeklyReportResponse,
    ClinicalPilotLaunchChecklistResponse,
    ClinicalVoiceQARunCreateRequest,
    ClinicalVoiceQARunResponse,
    ClinicalVoiceQAReportResponse,
    ClinicalViewerResponse,
    ClinicalPatentDossierResponse,
    ClinicalPatientResponse,
    ClinicalPersonaResponse,
    ClinicalProcedureResponse,
    ClinicalSlotBoardResponse,
    PreIntakeCreateRequest,
    PreIntakeResponse,
    PreIntakeUpdateRequest,
    ShadowReviewDecisionRequest,
    ShadowReviewResponse,
    SimulateWhatsAppRequest,
    VoiceCallSimulationRequest,
    WebhookIngestionResponse,
)
from app.services.clinical_compliance_service import build_compliance_profile, build_patent_dossier
from app.services.clinical_slot_service import build_slot_board
from app.services.clinical_service import (
    IncomingClinicalMessage,
    clinical_metrics,
    ensure_clinic_access,
    ensure_default_clinic,
    get_clinician_doctor,
    get_clinical_conversation,
    ingest_clinical_message,
    list_clinic_doctors,
    list_doctor_available_slots,
    list_doctor_inbox,
    list_clinical_conversations,
    list_shadow_reviews,
    parse_meta_payload,
    parse_twilio_form,
)
from app.services.clinical_appointment_service import (
    create_clinical_appointment_from_conversation,
    create_manual_clinical_appointment,
    recent_clinical_appointments,
    set_clinical_appointment_status,
    upcoming_clinical_appointments,
    update_appointment_clinical_details,
)
from app.services.clinical_feedback_service import (
    update_shadow_review,
)
from app.services.clinical_pre_intake_service import (
    create_pre_intake,
    get_pre_intake,
    list_pre_intakes,
    update_pre_intake,
)
from app.services.clinical_persona_service import list_personas
from app.services.pilot_metrics_service import (
    build_pilot_launch_checklist,
    build_pilot_metrics,
    build_pilot_weekly_report,
)


router = APIRouter(tags=["clinical"])


def message_payload(message) -> ClinicalMessageResponse:
    return ClinicalMessageResponse(
        id=message.id,
        conversation_id=message.conversation_id,
        sender=message.sender.value,
        content=message.content,
        language=message.language,
        intent=message.intent.value if message.intent else None,
        confidence_score=message.confidence_score,
        external_message_id=message.external_message_id,
        metadata_json=message.metadata_json,
        created_at=message.created_at,
    )


def patient_payload(patient) -> ClinicalPatientResponse:
    return ClinicalPatientResponse(
        id=patient.id,
        clinic_id=patient.clinic_id,
        full_name=patient.full_name,
        phone=patient.phone,
        language=patient.language,
        source=patient.source.value,
        created_at=patient.created_at,
        updated_at=patient.updated_at,
    )


def conversation_summary_payload(conversation: ClinicConversation) -> ClinicalConversationSummary:
    messages = conversation.messages or []
    last_preview = messages[-1].content[:100] if messages else None
    metadata = conversation.metadata_json or {}
    return ClinicalConversationSummary(
        id=conversation.id,
        clinic_id=conversation.clinic_id,
        patient=patient_payload(conversation.patient),
        channel=conversation.channel.value,
        status=conversation.status.value,
        language=conversation.language,
        intent=conversation.intent.value if conversation.intent else None,
        confidence_score=conversation.confidence_score,
        persona_name=metadata.get("last_persona_name"),
        last_urgency=metadata.get("last_urgency"),
        doctor_summary=metadata.get("doctor_summary"),
        possible_conditions=metadata.get("possible_conditions") or [],
        appointment_draft=metadata.get("appointment_draft"),
        metadata_json=metadata,
        doctor_inbox=conversation.status.value in {"waiting_human", "appointment_pending"},
        last_message_preview=last_preview,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


def conversation_detail_payload(conversation: ClinicConversation) -> ClinicalConversationDetail:
    summary = conversation_summary_payload(conversation)
    return ClinicalConversationDetail(**summary.model_dump(), messages=[message_payload(item) for item in conversation.messages])


def shadow_review_payload(review: ShadowReview) -> ShadowReviewResponse:
    metadata = review.metadata_json or {}
    return ShadowReviewResponse(
        id=review.id,
        clinic_id=review.clinic_id,
        conversation_id=review.conversation_id,
        patient_message_id=review.patient_message_id,
        assigned_doctor_id=review.assigned_doctor_id,
        assigned_doctor_name=review.assigned_doctor.full_name if review.assigned_doctor else None,
        assigned_doctor_specialty=review.assigned_doctor.specialty if review.assigned_doctor else None,
        draft_reply=review.draft_reply,
        intent=review.intent.value,
        confidence_score=review.confidence_score,
        risk_reason=review.risk_reason,
        status=review.status.value,
        persona_name=metadata.get("persona_name"),
        channel=metadata.get("channel"),
        final_reply=review.final_reply,
        metadata_json=review.metadata_json,
        created_at=review.created_at,
        updated_at=review.updated_at,
    )


def procedure_payload(procedure) -> ClinicalProcedureResponse:
    return ClinicalProcedureResponse(
        id=procedure.id,
        name=procedure.name,
        code=procedure.code,
        tooth=procedure.tooth,
        status=procedure.status.value,
        notes=procedure.notes,
        sort_order=procedure.sort_order,
        performed_by_doctor_id=procedure.performed_by_doctor_id,
        started_at=procedure.started_at,
        completed_at=procedure.completed_at,
    )


def appointment_payload(appointment: ClinicalAppointment) -> ClinicalAppointmentResponse:
    doctor_name = appointment.doctor.full_name if appointment.doctor else None
    return ClinicalAppointmentResponse(
        id=appointment.id,
        clinic_id=appointment.clinic_id,
        patient_id=appointment.patient_id,
        conversation_id=appointment.conversation_id,
        doctor_id=appointment.doctor_id,
        slot_id=appointment.slot_id,
        assigned_doctor_id=appointment.assigned_doctor_id,
        assigned_doctor_name=appointment.assigned_doctor.full_name if appointment.assigned_doctor else None,
        department=appointment.department,
        starts_at=appointment.starts_at,
        ends_at=appointment.ends_at,
        duration_minutes=appointment.duration_minutes,
        visit_reason=appointment.visit_reason,
        status=appointment.status.value,
        notes=appointment.notes,
        doctor_name=doctor_name,
        metadata_json=appointment.metadata_json,
        procedures=[procedure_payload(item) for item in appointment.procedures],
        created_at=appointment.created_at,
        updated_at=appointment.updated_at,
    )


def voice_qa_run_payload(run: ClinicalVoiceQARun) -> ClinicalVoiceQARunResponse:
    return ClinicalVoiceQARunResponse(
        id=run.id,
        clinic_id=run.clinic_id,
        tester=run.tester,
        device=run.device,
        browser=run.browser,
        audio_condition=run.audio_condition,
        voice_mode=run.voice_mode,
        scenario=run.scenario,
        mic_permission_seconds=run.mic_permission_seconds,
        first_assistant_audio_seconds=run.first_assistant_audio_seconds,
        transcript_correct=run.transcript_correct,
        transcript_shown=run.transcript_shown,
        retry_count=run.retry_count,
        completed_under_60s=run.completed_under_60s,
        appointment_created=run.appointment_created,
        operator_intervention=run.operator_intervention,
        emergency_guidance_shown=run.emergency_guidance_shown,
        severity=run.severity,
        notes=run.notes,
        metadata_json=run.metadata_json or {},
        created_at=run.created_at,
    )


def voice_qa_summary(runs: list[ClinicalVoiceQARun]) -> dict:
    total = len(runs)
    blocking = sum(1 for run in runs if run.severity == "blocking")
    major = sum(1 for run in runs if run.severity == "major")
    completed = sum(1 for run in runs if run.appointment_created)
    under_60 = sum(1 for run in runs if run.completed_under_60s)
    transcript_correct = sum(1 for run in runs if run.transcript_correct)
    retry_total = sum(run.retry_count for run in runs)
    return {
        "total_runs": total,
        "required_runs": 12,
        "blocking_failures": blocking,
        "major_failures": major,
        "appointment_success_rate": round((completed / total) * 100, 2) if total else 0.0,
        "under_60_rate": round((under_60 / total) * 100, 2) if total else 0.0,
        "transcript_correct_rate": round((transcript_correct / total) * 100, 2) if total else 0.0,
        "avg_retry_count": round(retry_total / total, 2) if total else 0.0,
        "ready_for_pilot": total >= 12 and blocking == 0 and major == 0,
    }


def ingestion_payload(result) -> WebhookIngestionResponse:
    # Triage çıktıları playground UI'da görünür. Mevcut konuşma ve son
    # AgentDecisionLog'tan çekiyoruz — IngestionResult zaten metadata taşır.
    conv = result.conversation
    risk = None
    requires_review = False
    persona_name = None
    risk_reason = None
    shadow = result.shadow_review
    if shadow is not None:
        risk = "high" if shadow.confidence_score < 0.6 else "medium"
        requires_review = True
        risk_reason = shadow.risk_reason
        persona_name = (shadow.metadata_json or {}).get("persona_name")
    return WebhookIngestionResponse(
        ok=True,
        clinic_id=result.clinic.id,
        patient_id=result.patient.id,
        conversation_id=conv.id,
        message_id=result.message.id,
        action=result.action,
        reply=result.reply,
        shadow_review_id=result.shadow_review.id if result.shadow_review else None,
        appointment_id=result.appointment.id if result.appointment else None,
    )


@router.get("/clinical/overview", response_model=ClinicalOverviewResponse)
def get_clinical_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ClinicalOverviewResponse:
    clinic = ensure_clinic_access(db, current_user, allow_clinician=True)
    doctor = get_clinician_doctor(db, clinic, current_user)
    conversations = [] if doctor else list_clinical_conversations(db, clinic, limit=20)
    doctor_items = list_doctor_inbox(db, clinic, limit=20, doctor_id=doctor.id if doctor else None)
    reviews = list_shadow_reviews(db, clinic, doctor_id=doctor.id if doctor else None)
    return ClinicalOverviewResponse(
        viewer=ClinicalViewerResponse(
            clinic_role="clinician" if doctor else ("owner" if current_user.role.name == RoleName.ADMIN else "operator"),
            doctor_id=doctor.id if doctor else None,
            doctor_name=doctor.full_name if doctor else None,
            specialty=doctor.specialty if doctor else None,
        ),
        metrics=ClinicalMetricsResponse(**clinical_metrics(db, clinic, doctor_id=doctor.id if doctor else None)),
        conversations=[conversation_summary_payload(item) for item in conversations],
        doctor_inbox=[conversation_summary_payload(item) for item in doctor_items],
        shadow_reviews=[shadow_review_payload(item) for item in reviews],
    )


@router.get("/clinical/pilot-metrics", response_model=ClinicalPilotMetricsResponse)
def get_clinical_pilot_metrics(
    days: int = Query(default=7, ge=1, le=90),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ClinicalPilotMetricsResponse:
    clinic = ensure_clinic_access(db, current_user, allow_clinician=True)
    return ClinicalPilotMetricsResponse(**build_pilot_metrics(db, clinic, days=days))


@router.get("/clinical/pilot-weekly-report", response_model=ClinicalPilotWeeklyReportResponse)
def get_clinical_pilot_weekly_report(
    days: int = Query(default=7, ge=1, le=90),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ClinicalPilotWeeklyReportResponse:
    clinic = ensure_clinic_access(db, current_user, allow_clinician=True)
    return ClinicalPilotWeeklyReportResponse(**build_pilot_weekly_report(db, clinic, days=days))


@router.get("/clinical/pilot-launch-checklist", response_model=ClinicalPilotLaunchChecklistResponse)
def get_clinical_pilot_launch_checklist(
    days: int = Query(default=7, ge=1, le=90),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ClinicalPilotLaunchChecklistResponse:
    clinic = ensure_clinic_access(db, current_user, allow_clinician=True)
    return ClinicalPilotLaunchChecklistResponse(**build_pilot_launch_checklist(db, clinic, days=days))


@router.get("/clinical/voice-qa-runs", response_model=ClinicalVoiceQAReportResponse)
def get_clinical_voice_qa_runs(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ClinicalVoiceQAReportResponse:
    clinic = ensure_clinic_access(db, current_user, allow_clinician=True)
    runs = db.scalars(
        select(ClinicalVoiceQARun)
        .where(ClinicalVoiceQARun.clinic_id == clinic.id)
        .order_by(ClinicalVoiceQARun.created_at.desc(), ClinicalVoiceQARun.id.desc())
        .limit(limit)
    ).all()
    return ClinicalVoiceQAReportResponse(
        summary=voice_qa_summary(list(runs)),
        runs=[voice_qa_run_payload(run) for run in runs],
    )


@router.post("/clinical/voice-qa-runs", response_model=ClinicalVoiceQARunResponse)
def create_clinical_voice_qa_run(
    payload: ClinicalVoiceQARunCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ClinicalVoiceQARunResponse:
    clinic = ensure_clinic_access(db, current_user, allow_clinician=True)
    run = ClinicalVoiceQARun(
        clinic_id=clinic.id,
        **payload.model_dump(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return voice_qa_run_payload(run)


@router.get("/clinical/personas", response_model=list[ClinicalPersonaResponse])
def get_clinical_personas() -> list[ClinicalPersonaResponse]:
    return [ClinicalPersonaResponse(**persona.__dict__) for persona in list_personas()]


@router.get("/clinical/compliance-profile", response_model=ClinicalComplianceProfileResponse)
def get_clinical_compliance_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ClinicalComplianceProfileResponse:
    clinic = ensure_clinic_access(db, current_user, allow_clinician=True)
    return ClinicalComplianceProfileResponse(**build_compliance_profile(clinic))


@router.get("/clinical/patent-dossier", response_model=ClinicalPatentDossierResponse)
def get_clinical_patent_dossier(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ClinicalPatentDossierResponse:
    clinic = ensure_clinic_access(db, current_user, allow_clinician=True)
    return ClinicalPatentDossierResponse(**build_patent_dossier(clinic))


@router.get("/clinical/slot-board", response_model=ClinicalSlotBoardResponse)
def get_clinical_slot_board(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ClinicalSlotBoardResponse:
    ensure_clinic_access(db, current_user, allow_clinician=True)
    return ClinicalSlotBoardResponse(**build_slot_board())


@router.get("/clinical/doctors", response_model=list[ClinicDoctorResponse])
def get_clinic_doctors(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ClinicDoctorResponse]:
    clinic = ensure_clinic_access(db, current_user)
    doctors = list_clinic_doctors(db, clinic)
    return [ClinicDoctorResponse.model_validate(d) for d in doctors]


@router.get("/clinical/doctors/{doctor_id}/slots", response_model=list[ClinicDoctorSlotResponse])
def get_doctor_slots(
    doctor_id: int,
    date: str | None = Query(default=None, description="ISO date YYYY-MM-DD, defaults to today"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ClinicDoctorSlotResponse]:
    clinic = ensure_clinic_access(db, current_user)
    slots = list_doctor_available_slots(db, clinic, doctor_id, date)
    return [
        ClinicDoctorSlotResponse(
            id=s.id,
            doctor_id=s.doctor_id,
            clinic_id=s.clinic_id,
            start_time=s.start_time,
            end_time=s.end_time,
            is_booked=s.is_booked,
            is_blocked=s.is_blocked,
            doctor_name=s.doctor.full_name if s.doctor else None,
            specialty=s.doctor.specialty if s.doctor else None,
        )
        for s in slots
    ]


@router.get("/clinical/doctor-inbox", response_model=list[ClinicalConversationSummary])
def get_doctor_inbox(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ClinicalConversationSummary]:
    clinic = ensure_clinic_access(db, current_user)
    return [conversation_summary_payload(item) for item in list_doctor_inbox(db, clinic)]


@router.get("/clinical/appointments/upcoming", response_model=list[ClinicalAppointmentResponse])
def get_upcoming_clinical_appointments(
    # Max window 30 gün (43200 dk) — klinik takvim sayfası tüm haftayı +
    # bir kaç haftayı bir bakışta görebilsin. Eski caller'lar (120 dk
    # default) etkilenmez.
    within_minutes: int = Query(default=120, ge=5, le=43200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ClinicalAppointmentResponse]:
    clinic = ensure_clinic_access(db, current_user, allow_clinician=True)
    doctor = get_clinician_doctor(db, clinic, current_user)
    return [
        appointment_payload(item)
        for item in upcoming_clinical_appointments(
            db,
            clinic,
            within_minutes,
            doctor_id=doctor.id if doctor else None,
        )
    ]


@router.post("/clinical/appointments", response_model=ClinicalAppointmentResponse)
def post_clinical_appointment(
    payload: ClinicalAppointmentCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ClinicalAppointmentResponse:
    clinic = ensure_clinic_access(db, current_user)
    appointment = create_clinical_appointment_from_conversation(
        db,
        clinic,
        conversation_id=payload.conversation_id,
        department=payload.department,
        starts_at=payload.starts_at,
        duration_minutes=payload.duration_minutes,
        visit_reason=payload.visit_reason,
        notes=payload.notes,
        doctor_id=payload.doctor_id,
        slot_id=payload.slot_id,
    )
    return appointment_payload(appointment)


def appointment_row_payload(db: Session, appointment: ClinicalAppointment) -> ClinicalAppointmentRow:
    """Randevuyu hasta adı, hekim ve şube bilgisiyle zenginleştirir."""
    patient = db.get(ClinicPatient, appointment.patient_id)
    branch = db.get(ClinicBranch, appointment.branch_id) if appointment.branch_id else None
    metadata = appointment.metadata_json or {}
    return ClinicalAppointmentRow(
        id=appointment.id,
        patient_id=appointment.patient_id,
        patient_name=patient.full_name if patient else None,
        patient_phone=patient.phone if patient else None,
        conversation_id=appointment.conversation_id,
        assigned_doctor_id=appointment.assigned_doctor_id,
        department=appointment.department,
        physician_name=metadata.get("physician_name") or (
            appointment.assigned_doctor.full_name if appointment.assigned_doctor else None
        ),
        branch_name=branch.name if branch else None,
        starts_at=appointment.starts_at,
        ends_at=appointment.ends_at,
        duration_minutes=appointment.duration_minutes,
        visit_reason=appointment.visit_reason,
        status=appointment.status.value,
        notes=appointment.notes,
        procedures=[procedure_payload(item) for item in appointment.procedures],
        created_at=appointment.created_at,
    )


@router.get("/clinical/appointments", response_model=list[ClinicalAppointmentRow])
def list_clinical_appointments(
    limit: int = Query(default=50, ge=1, le=200),
    doctor_id: int | None = Query(default=None, ge=1),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ClinicalAppointmentRow]:
    clinic = ensure_clinic_access(db, current_user, allow_clinician=True)
    doctor = get_clinician_doctor(db, clinic, current_user)
    scoped_doctor_id = doctor.id if doctor else doctor_id
    return [
        appointment_row_payload(db, item)
        for item in recent_clinical_appointments(
            db,
            clinic,
            limit,
            doctor_id=scoped_doctor_id,
            date_from=date_from,
            date_to=date_to,
        )
    ]


@router.post("/clinical/appointments/manual", response_model=ClinicalAppointmentRow)
def post_clinical_manual_appointment(
    payload: ClinicalManualAppointmentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ClinicalAppointmentRow:
    """Operatör slot panosundan veya panelden manuel randevu açar."""
    clinic = ensure_clinic_access(db, current_user)
    appointment = create_manual_clinical_appointment(
        db,
        clinic,
        full_name=payload.full_name,
        phone=payload.phone,
        department=payload.department,
        starts_at=payload.starts_at,
        duration_minutes=payload.duration_minutes,
        visit_reason=payload.visit_reason,
        physician_name=payload.physician_name,
        branch_name=payload.branch_name,
        notes=payload.notes,
    )
    return appointment_row_payload(db, appointment)


@router.patch("/clinical/appointments/{appointment_id}/clinical-details", response_model=ClinicalAppointmentRow)
def patch_clinical_appointment_details(
    appointment_id: int,
    payload: ClinicalAppointmentDetailsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ClinicalAppointmentRow:
    clinic = ensure_clinic_access(db, current_user, allow_clinician=True)
    doctor = get_clinician_doctor(db, clinic, current_user)
    appointment = update_appointment_clinical_details(
        db,
        clinic,
        appointment_id,
        doctor_id=doctor.id if doctor else None,
        starts_at=payload.starts_at,
        duration_minutes=payload.duration_minutes,
        visit_reason=payload.visit_reason,
        notes=payload.notes,
        procedures=[item.model_dump() for item in payload.procedures] if payload.procedures is not None else None,
        fields_set=set(payload.model_fields_set),
    )
    return appointment_row_payload(db, appointment)


@router.post("/clinical/appointments/{appointment_id}/status", response_model=ClinicalAppointmentRow)
def post_clinical_appointment_status(
    appointment_id: int,
    payload: ClinicalAppointmentStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ClinicalAppointmentRow:
    clinic = ensure_clinic_access(db, current_user, allow_clinician=True)
    doctor = get_clinician_doctor(db, clinic, current_user)
    appointment = set_clinical_appointment_status(
        db,
        clinic,
        appointment_id,
        payload.status,
        doctor_id=doctor.id if doctor else None,
    )
    return appointment_row_payload(db, appointment)


@router.get("/clinical/conversations/{conversation_id}", response_model=ClinicalConversationDetail)
def get_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ClinicalConversationDetail:
    clinic = ensure_clinic_access(db, current_user)
    return conversation_detail_payload(get_clinical_conversation(db, clinic, conversation_id))


@router.get("/clinical/shadow-reviews", response_model=list[ShadowReviewResponse])
def get_shadow_reviews(
    status: str | None = Query(default="pending"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ShadowReviewResponse]:
    clinic = ensure_clinic_access(db, current_user, allow_clinician=True)
    doctor = get_clinician_doctor(db, clinic, current_user)
    status_filter = ShadowReviewStatus(status) if status else None
    return [
        shadow_review_payload(item)
        for item in list_shadow_reviews(db, clinic, status_filter, doctor_id=doctor.id if doctor else None)
    ]


@router.patch("/clinical/shadow-reviews/{review_id}", response_model=ShadowReviewResponse)
def patch_shadow_review(
    review_id: int,
    payload: ShadowReviewDecisionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ShadowReviewResponse:
    clinic = ensure_clinic_access(db, current_user, allow_clinician=True)
    doctor = get_clinician_doctor(db, clinic, current_user)
    review = update_shadow_review(
        db,
        clinic,
        current_user,
        review_id,
        payload.status,
        payload.final_reply,
        doctor_id=doctor.id if doctor else None,
    )
    return shadow_review_payload(review)


@router.post("/clinical/simulate-whatsapp", response_model=WebhookIngestionResponse)
def simulate_whatsapp(
    payload: SimulateWhatsAppRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WebhookIngestionResponse:
    clinic = ensure_clinic_access(db, current_user)
    result = ingest_clinical_message(
        db,
        IncomingClinicalMessage(
            from_phone=payload.from_phone,
            body=payload.body,
            channel=ClinicChannel.WHATSAPP,
            patient_name=payload.patient_name,
            raw_payload={"simulated_by_user_id": current_user.id},
        ),
        clinic=clinic,
    )
    return ingestion_payload(result)


@router.post("/clinical/simulate-voice-call", response_model=WebhookIngestionResponse)
def simulate_voice_call(
    payload: VoiceCallSimulationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WebhookIngestionResponse:
    clinic = ensure_clinic_access(db, current_user)
    result = ingest_clinical_message(
        db,
        IncomingClinicalMessage(
            from_phone=payload.from_phone,
            body=payload.speech,
            channel=ClinicChannel.PHONE,
            patient_name=payload.patient_name,
            requested_persona_id=payload.persona_id,
            raw_payload={"simulated_voice_by_user_id": current_user.id},
        ),
        clinic=clinic,
    )
    return ingestion_payload(result)


def pre_intake_payload(pre_intake) -> PreIntakeResponse:
    return PreIntakeResponse(
        id=pre_intake.id,
        clinic_id=pre_intake.clinic_id,
        patient_id=pre_intake.patient_id,
        conversation_id=pre_intake.conversation_id,
        answers_json=pre_intake.answers_json or {},
        is_complete=pre_intake.is_complete,
        created_at=pre_intake.created_at,
        updated_at=pre_intake.updated_at,
    )


@router.post("/clinical/pre-intakes", response_model=PreIntakeResponse)
def post_pre_intake(
    payload: PreIntakeCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PreIntakeResponse:
    clinic = ensure_clinic_access(db, current_user)
    pre_intake = create_pre_intake(
        db,
        clinic,
        patient_id=payload.patient_id,
        conversation_id=payload.conversation_id,
        answers=payload.answers,
        is_complete=payload.is_complete,
    )
    return pre_intake_payload(pre_intake)


@router.get("/clinical/pre-intakes", response_model=list[PreIntakeResponse])
def get_pre_intakes(
    patient_id: int | None = Query(default=None),
    conversation_id: int | None = Query(default=None),
    is_complete: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[PreIntakeResponse]:
    clinic = ensure_clinic_access(db, current_user)
    items = list_pre_intakes(
        db,
        clinic,
        patient_id=patient_id,
        conversation_id=conversation_id,
        is_complete=is_complete,
        limit=limit,
    )
    return [pre_intake_payload(item) for item in items]


@router.get("/clinical/pre-intakes/{pre_intake_id}", response_model=PreIntakeResponse)
def get_pre_intake_detail(
    pre_intake_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PreIntakeResponse:
    clinic = ensure_clinic_access(db, current_user)
    return pre_intake_payload(get_pre_intake(db, clinic, pre_intake_id))


@router.patch("/clinical/pre-intakes/{pre_intake_id}", response_model=PreIntakeResponse)
def patch_pre_intake(
    pre_intake_id: int,
    payload: PreIntakeUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PreIntakeResponse:
    clinic = ensure_clinic_access(db, current_user)
    pre_intake = update_pre_intake(
        db,
        clinic,
        pre_intake_id,
        answers=payload.answers,
        is_complete=payload.is_complete,
        replace=payload.replace,
    )
    return pre_intake_payload(pre_intake)


def _voice_twiml(message: str, action_url: str = "/api/webhooks/voice/gather") -> str:
    escaped_message = escape(message, quote=True)
    escaped_action = escape(action_url, quote=True)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Gather input="speech" language="tr-TR" speechTimeout="auto" action="{escaped_action}" method="POST">
    <Say language="tr-TR" voice="alice">{escaped_message}</Say>
  </Gather>
  <Say language="tr-TR" voice="alice">Sizi anlayamadım. Lütfen tekrar arayın veya kliniğe WhatsApp üzerinden yazın.</Say>
</Response>"""


def _verify_twilio_voice_request(request: Request, body: bytes) -> None:
    if not signature_required():
        return
    settings = get_settings()
    twilio_sig = request.headers.get("X-Twilio-Signature")
    form_params = {key: values[0] if values else "" for key, values in parse_qs(body.decode("utf-8")).items()}
    if not verify_twilio_signature(
        auth_token=settings.twilio_auth_token,
        request_url=_webhook_request_url(request),
        form_params=form_params,
        signature_header=twilio_sig,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Twilio signature",
        )


@router.post("/webhooks/voice/incoming")
async def receive_voice_call(request: Request) -> PlainTextResponse:
    body = await request.body()
    _verify_twilio_voice_request(request, body)
    parsed = dict((key, values[0] if values else "") for key, values in parse_qs(body.decode("utf-8")).items())
    caller = parsed.get("From", "hasta")
    prompt = (
        "CogniVault medikal asistanına hoş geldiniz. Ben Selin. "
        "Randevu, sigorta, fiyat veya doktorunuza iletilmesini istediğiniz sağlık talebinizi kısaca söyleyin."
    )
    if caller:
        prompt += " Konuşmanız doktor ekranına güvenli şekilde not olarak düşecektir."
    return PlainTextResponse(_voice_twiml(prompt), media_type="application/xml")


@router.post("/webhooks/voice/gather")
async def receive_voice_speech(request: Request, db: Session = Depends(get_db)) -> PlainTextResponse:
    body = await request.body()
    _verify_twilio_voice_request(request, body)
    parsed = dict((key, values[0] if values else "") for key, values in parse_qs(body.decode("utf-8")).items())
    speech = (parsed.get("SpeechResult") or "").strip()
    from_phone = parsed.get("From") or parsed.get("Caller") or "unknown-caller"
    call_sid = parsed.get("CallSid")

    if not speech:
        return PlainTextResponse(
            _voice_twiml("Sizi net duyamadım. Lütfen talebinizi tekrar söyler misiniz?"),
            media_type="application/xml",
        )

    clinic = ensure_default_clinic(db)
    # CallSid çağrı boyunca sabittir; tek başına idempotency anahtarı yapılırsa
    # ikinci hasta cümlesi yanlışlıkla duplicate sayılır. Aynı webhook retry'ı
    # yine aynı anahtarı üretirken farklı konuşma turları ayrı kaydolur.
    speech_fingerprint = hashlib.sha256(speech.encode("utf-8")).hexdigest()[:16]
    turn_id = f"{call_sid}:{speech_fingerprint}" if call_sid else None
    result = ingest_clinical_message(
        db,
        IncomingClinicalMessage(
            from_phone=from_phone,
            body=speech,
            channel=ClinicChannel.PHONE,
            external_message_id=turn_id,
            external_thread_id=call_sid or from_phone,
            raw_payload=parsed,
        ),
        clinic=clinic,
    )
    reply = result.reply
    if result.shadow_review is not None:
        reply = (
            "Talebinizi aldım ve doktor ekranına öncelikli olarak düşürdüm. "
            "Tıbbi güvenlik gerektiren konularda insan onayı olmadan kesin yönlendirme yapmıyorum."
        )
    return PlainTextResponse(_voice_twiml(reply or "Talebinizi aldım. Size nasıl devam edebilirim?"), media_type="application/xml")


@router.post("/webhooks/voice/status")
async def receive_voice_status(request: Request, db: Session = Depends(get_db)) -> PlainTextResponse:
    """Persist Twilio's terminal/non-terminal call lifecycle without copying audio."""
    body = await request.body()
    _verify_twilio_voice_request(request, body)
    parsed = dict((key, values[0] if values else "") for key, values in parse_qs(body.decode("utf-8")).items())
    call_sid = (parsed.get("CallSid") or "").strip()
    call_status = (parsed.get("CallStatus") or "unknown").strip().lower()
    if not call_sid:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="CallSid is required")

    conversation = db.scalars(
        select(ClinicConversation)
        .where(ClinicConversation.external_thread_id == call_sid)
        .order_by(ClinicConversation.updated_at.desc())
    ).first()
    if conversation is None:
        # Status callback konuşma turundan önce ulaşabilir; Twilio retry etmesin.
        return PlainTextResponse("ignored", status_code=status.HTTP_202_ACCEPTED)

    terminal = call_status in {"completed", "busy", "no-answer", "failed", "canceled"}
    metadata = {
        **(conversation.metadata_json or {}),
        "voice_call": {
            "call_sid": call_sid,
            "status": call_status,
            "duration_seconds": int(parsed["CallDuration"]) if parsed.get("CallDuration", "").isdigit() else None,
            "terminal": terminal,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    }
    conversation.metadata_json = metadata
    db.add(conversation)
    db.commit()
    return PlainTextResponse("ok")


@router.get("/webhooks/whatsapp")
def verify_meta_webhook(
    request: Request,
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
) -> PlainTextResponse:
    from app.core.config import get_settings

    settings = get_settings()
    if hub_mode == "subscribe" and hub_verify_token and hub_verify_token == settings.meta_verify_token:
        return PlainTextResponse(hub_challenge or "")
    return PlainTextResponse("verification failed", status_code=403)


def _webhook_request_url(request: Request) -> str:
    base = get_settings().clinical_webhook_base_url.strip()
    if base:
        return base.rstrip("/") + request.url.path
    return str(request.url)


@router.post("/webhooks/whatsapp", response_model=list[WebhookIngestionResponse] | WebhookIngestionResponse)
async def receive_whatsapp_webhook(request: Request, db: Session = Depends(get_db)):
    content_type = request.headers.get("content-type", "")
    settings = get_settings()
    clinic = ensure_default_clinic(db)

    raw_body = await request.body()

    if "application/x-www-form-urlencoded" in content_type:
        # Twilio inbound: validate the X-Twilio-Signature header against the canonical request.
        if signature_required():
            twilio_sig = request.headers.get("X-Twilio-Signature")
            from urllib.parse import parse_qs

            form_params = {
                key: values[0] if values else ""
                for key, values in parse_qs(raw_body.decode("utf-8")).items()
            }
            if not verify_twilio_signature(
                auth_token=settings.twilio_auth_token,
                request_url=_webhook_request_url(request),
                form_params=form_params,
                signature_header=twilio_sig,
            ):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid Twilio signature",
                )
        incoming = parse_twilio_form(raw_body)
        return ingestion_payload(ingest_clinical_message(db, incoming, clinic=clinic))

    # Meta Cloud API inbound: validate the X-Hub-Signature-256 header against the raw body.
    if signature_required():
        meta_sig = request.headers.get("X-Hub-Signature-256")
        if not verify_meta_signature(
            app_secret=settings.meta_app_secret,
            raw_body=raw_body,
            signature_header=meta_sig,
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Meta signature",
            )
    import json

    payload = json.loads(raw_body or b"{}")
    messages = parse_meta_payload(payload)
    results = [ingestion_payload(ingest_clinical_message(db, item, clinic=clinic)) for item in messages]
    return results


# ─── KVKK Md. 11 — Silme Hakkı (Right to Erasure) ──────────────────────────
@router.delete("/clinical/patients/{patient_id}/erasure")
def erase_patient_data(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, object]:
    """KVKK Md. 11 silme hakkı — hasta verisini anonymize eder.

    Bu işlem geri alınamaz. Sadece operator veya admin rolü tetikleyebilir.
    Tüm adımlar AuditLog'a `action_type="right_to_erasure"` olarak yazılır.

    Anonymization stratejisi:
      - ClinicPatient.full_name → "[SİLİNDİ]"
      - ClinicPatient.phone → SHA-256(phone + clinic_pepper) — telefon hâlâ
        eşsiz tutulmalı (UniqueConstraint), düz silinemez.
      - ClinicMessage.content → "[İçerik KVKK gereği silindi]"
      - ShadowReview.draft_reply / final_reply → "[Silindi]"
      - ConsentRecord.withdrawn_at → şimdi (rıza geri çekildi olarak işaretle)
    """
    import hashlib
    from datetime import datetime, timezone

    from app.services.audit_service import log_action

    # KVKK silme hakkını sadece operator/admin tetikleyebilir
    if current_user.role.name not in (RoleName.OPERATOR, RoleName.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Silme hakkı yalnızca operatör veya yönetici tarafından kullanılabilir (KVKK Md. 11).",
        )

    patient = db.get(ClinicPatient, patient_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hasta bulunamadı")

    # Klinik scope kontrolü — operatörün kendi kliniği dışındaki hastaya erişimi yasak
    clinic = ensure_clinic_access(db, current_user)
    if patient.clinic_id != clinic.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hasta bulunamadı")

    now = datetime.now(timezone.utc)
    settings_obj = get_settings()
    # Tuz: JWT secret + clinic id (klinik bazlı, geri-türetilemeyen)
    pepper = f"{settings_obj.jwt_secret}:{clinic.id}".encode()

    # 1) Hasta kimliği anonymization
    original_phone = patient.phone
    hashed_phone = hashlib.sha256(original_phone.encode() + pepper).hexdigest()[:32]
    patient.full_name = "[SİLİNDİ]"
    patient.phone = f"erased:{hashed_phone}"
    patient.metadata_json = {}
    patient.external_ref = None

    # 2) Konuşma mesajlarını anonymize et
    messages = db.scalars(
        select(ClinicMessage).where(ClinicMessage.conversation_id.in_(
            select(ClinicConversation.id).where(ClinicConversation.patient_id == patient.id)
        ))
    ).all()
    erased_message_count = 0
    for msg in messages:
        msg.content = "[İçerik KVKK gereği silindi]"
        msg.metadata_json = {"erased": True}
        erased_message_count += 1

    # 3) Shadow review draft + final reply'leri anonymize et
    reviews = db.scalars(
        select(ShadowReview).where(ShadowReview.conversation_id.in_(
            select(ClinicConversation.id).where(ClinicConversation.patient_id == patient.id)
        ))
    ).all()
    erased_review_count = 0
    for review in reviews:
        review.draft_reply = "[Silindi]"
        if review.final_reply:
            review.final_reply = "[Silindi]"
        erased_review_count += 1

    # 4) Tüm rıza kayıtlarını geri çek
    consents = db.scalars(
        select(ConsentRecord).where(
            ConsentRecord.patient_id == patient.id,
            ConsentRecord.withdrawn_at.is_(None),
        )
    ).all()
    for consent in consents:
        consent.withdrawn_at = now

    db.commit()

    # 5) Tüm bu adımları tek bir audit kaydı altında topla
    log_action(
        db,
        user_id=current_user.id,
        action_type="right_to_erasure",
        explanation=f"KVKK Md. 11 silme hakkı — hasta #{patient_id} verileri anonymize edildi.",
        result_status=AuditResultStatus.SUCCESS,
        clinic_id=clinic.id,
        organization_id=current_user.organization_id,
        details={
            "patient_id": patient_id,
            "messages_erased": erased_message_count,
            "shadow_reviews_erased": erased_review_count,
            "consents_withdrawn": len(consents),
        },
    )

    return {
        "patient_id": patient_id,
        "erased_at": now.isoformat(),
        "messages_erased": erased_message_count,
        "shadow_reviews_erased": erased_review_count,
        "consents_withdrawn": len(consents),
    }
