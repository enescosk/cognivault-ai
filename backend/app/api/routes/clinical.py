from __future__ import annotations

from html import escape
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.models import ClinicChannel, ClinicConversation, ClinicDoctor, ClinicDoctorSlot, ClinicalAppointment, ShadowReview, ShadowReviewStatus, User
from app.schemas.clinical import (
    ClinicalAppointmentCreateRequest,
    ClinicalAppointmentResponse,
    ClinicDoctorResponse,
    ClinicDoctorSlotResponse,
    ClinicalConversationDetail,
    ClinicalConversationSummary,
    ClinicalMessageResponse,
    ClinicalMetricsResponse,
    ClinicalOverviewResponse,
    ClinicalPatientResponse,
    ClinicalPersonaResponse,
    ShadowReviewDecisionRequest,
    ShadowReviewResponse,
    SimulateWhatsAppRequest,
    VoiceCallSimulationRequest,
    WebhookIngestionResponse,
)
from app.services.clinical_service import (
    IncomingClinicalMessage,
    clinical_metrics,
    create_clinical_appointment_from_conversation,
    ensure_clinic_access,
    ensure_default_clinic,
    get_clinical_conversation,
    ingest_clinical_message,
    list_clinic_doctors,
    list_doctor_available_slots,
    list_doctor_inbox,
    list_clinical_conversations,
    list_shadow_reviews,
    parse_meta_payload,
    parse_twilio_form,
    upcoming_clinical_appointments,
    update_shadow_review,
)
from app.services.clinical_persona_service import list_personas


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


def appointment_payload(appointment: ClinicalAppointment) -> ClinicalAppointmentResponse:
    doctor_name = appointment.doctor.full_name if appointment.doctor else None
    return ClinicalAppointmentResponse(
        id=appointment.id,
        clinic_id=appointment.clinic_id,
        patient_id=appointment.patient_id,
        conversation_id=appointment.conversation_id,
        doctor_id=appointment.doctor_id,
        slot_id=appointment.slot_id,
        department=appointment.department,
        starts_at=appointment.starts_at,
        status=appointment.status.value,
        notes=appointment.notes,
        doctor_name=doctor_name,
        metadata_json=appointment.metadata_json,
        created_at=appointment.created_at,
        updated_at=appointment.updated_at,
    )


def ingestion_payload(result) -> WebhookIngestionResponse:
    return WebhookIngestionResponse(
        ok=True,
        clinic_id=result.clinic.id,
        patient_id=result.patient.id,
        conversation_id=result.conversation.id,
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
    clinic = ensure_clinic_access(db, current_user)
    conversations = list_clinical_conversations(db, clinic, limit=20)
    doctor_items = list_doctor_inbox(db, clinic, limit=20)
    reviews = list_shadow_reviews(db, clinic)
    return ClinicalOverviewResponse(
        metrics=ClinicalMetricsResponse(**clinical_metrics(db, clinic)),
        conversations=[conversation_summary_payload(item) for item in conversations],
        doctor_inbox=[conversation_summary_payload(item) for item in doctor_items],
        shadow_reviews=[shadow_review_payload(item) for item in reviews],
    )


@router.get("/clinical/personas", response_model=list[ClinicalPersonaResponse])
def get_clinical_personas() -> list[ClinicalPersonaResponse]:
    return [ClinicalPersonaResponse(**persona.__dict__) for persona in list_personas()]


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
    within_minutes: int = Query(default=120, ge=5, le=1440),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ClinicalAppointmentResponse]:
    clinic = ensure_clinic_access(db, current_user)
    return [appointment_payload(item) for item in upcoming_clinical_appointments(db, clinic, within_minutes)]


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
        notes=payload.notes,
        doctor_id=payload.doctor_id,
        slot_id=payload.slot_id,
    )
    return appointment_payload(appointment)


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
    clinic = ensure_clinic_access(db, current_user)
    status_filter = ShadowReviewStatus(status) if status else None
    return [shadow_review_payload(item) for item in list_shadow_reviews(db, clinic, status_filter)]


@router.patch("/clinical/shadow-reviews/{review_id}", response_model=ShadowReviewResponse)
def patch_shadow_review(
    review_id: int,
    payload: ShadowReviewDecisionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ShadowReviewResponse:
    clinic = ensure_clinic_access(db, current_user)
    review = update_shadow_review(db, clinic, current_user, review_id, payload.status, payload.final_reply)
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


@router.post("/webhooks/voice/incoming")
async def receive_voice_call(request: Request) -> PlainTextResponse:
    body = await request.body()
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
    result = ingest_clinical_message(
        db,
        IncomingClinicalMessage(
            from_phone=from_phone,
            body=speech,
            channel=ClinicChannel.PHONE,
            external_message_id=call_sid,
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


@router.post("/webhooks/whatsapp", response_model=list[WebhookIngestionResponse] | WebhookIngestionResponse)
async def receive_whatsapp_webhook(request: Request, db: Session = Depends(get_db)):
    content_type = request.headers.get("content-type", "")
    clinic = ensure_default_clinic(db)

    if "application/x-www-form-urlencoded" in content_type:
        incoming = parse_twilio_form(await request.body())
        return ingestion_payload(ingest_clinical_message(db, incoming, clinic=clinic))

    payload = await request.json()
    messages = parse_meta_payload(payload)
    results = [ingestion_payload(ingest_clinical_message(db, item, clinic=clinic)) for item in messages]
    return results
