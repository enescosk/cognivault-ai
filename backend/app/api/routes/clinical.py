from __future__ import annotations

from html import escape
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.core.config import get_settings
from app.core.webhook_security import (
    signature_required,
    verify_meta_signature,
    verify_twilio_signature,
)
from app.models import ClinicChannel, ClinicConversation, ClinicalAppointment, ShadowReview, ShadowReviewStatus, User
from app.schemas.clinical import (
    ClinicalAppointmentCreateRequest,
    ClinicalAppointmentResponse,
    ClinicalComplianceProfileResponse,
    ClinicalConversationDetail,
    ClinicalConversationSummary,
    ClinicalMessageResponse,
    ClinicalMetricsResponse,
    ClinicalOverviewResponse,
    ClinicalPatentDossierResponse,
    ClinicalPatientResponse,
    ClinicalPersonaResponse,
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
    create_clinical_appointment_from_conversation,
    create_pre_intake,
    ensure_clinic_access,
    ensure_default_clinic,
    get_clinical_conversation,
    get_pre_intake,
    ingest_clinical_message,
    list_doctor_inbox,
    list_clinical_conversations,
    list_pre_intakes,
    list_shadow_reviews,
    parse_meta_payload,
    parse_twilio_form,
    upcoming_clinical_appointments,
    update_pre_intake,
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
    return ClinicalAppointmentResponse(
        id=appointment.id,
        clinic_id=appointment.clinic_id,
        patient_id=appointment.patient_id,
        conversation_id=appointment.conversation_id,
        department=appointment.department,
        starts_at=appointment.starts_at,
        status=appointment.status.value,
        notes=appointment.notes,
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


@router.get("/clinical/compliance-profile", response_model=ClinicalComplianceProfileResponse)
def get_clinical_compliance_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ClinicalComplianceProfileResponse:
    clinic = ensure_clinic_access(db, current_user)
    return ClinicalComplianceProfileResponse(**build_compliance_profile(clinic))


@router.get("/clinical/patent-dossier", response_model=ClinicalPatentDossierResponse)
def get_clinical_patent_dossier(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ClinicalPatentDossierResponse:
    clinic = ensure_clinic_access(db, current_user)
    return ClinicalPatentDossierResponse(**build_patent_dossier(clinic))


@router.get("/clinical/slot-board", response_model=ClinicalSlotBoardResponse)
def get_clinical_slot_board(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ClinicalSlotBoardResponse:
    ensure_clinic_access(db, current_user)
    return ClinicalSlotBoardResponse(**build_slot_board())


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
