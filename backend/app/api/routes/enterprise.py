from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.models import Department, EnterpriseSession, EnterpriseTicket, User
from app.schemas.appointment import AppointmentResponse
from app.schemas.enterprise import (
    DepartmentResponse,
    EnterpriseCustomerResponse,
    EnterpriseDecisionResponse,
    EnterpriseMessageRequest,
    EnterpriseMessageResponse,
    EnterpriseMetricsResponse,
    EnterpriseOverviewResponse,
    EnterpriseSessionCreateRequest,
    EnterpriseSessionDetail,
    EnterpriseSessionSummary,
    EnterpriseTicketStatusUpdateRequest,
    EnterpriseTicketResponse,
    OrganizationResponse,
)
from app.services.appointment_service import appointment_payload
from app.services.enterprise_service import (
    create_enterprise_session,
    enterprise_metrics,
    get_enterprise_session,
    list_departments,
    list_enterprise_sessions,
    list_enterprise_tickets,
    process_enterprise_message,
    update_enterprise_ticket_status,
)


router = APIRouter(prefix="/enterprise", tags=["enterprise"])


def department_payload(department: Department | None) -> DepartmentResponse | None:
    if department is None:
        return None
    return DepartmentResponse.model_validate(department)


def customer_payload(session_or_ticket) -> EnterpriseCustomerResponse:
    return EnterpriseCustomerResponse.model_validate(session_or_ticket.customer)


def ticket_payload(ticket: EnterpriseTicket) -> EnterpriseTicketResponse:
    return EnterpriseTicketResponse(
        id=ticket.id,
        session_id=ticket.session_id,
        customer=customer_payload(ticket),
        department=department_payload(ticket.department),
        intent=ticket.intent,
        description=ticket.description,
        status=ticket.status.value,
        priority=ticket.priority,
        confidence=ticket.confidence,
        handoff_package=ticket.handoff_package,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
    )


def session_summary_payload(session: EnterpriseSession) -> EnterpriseSessionSummary:
    messages = session.chat_session.messages if session.chat_session else []
    last_preview = messages[-1].content[:90] if messages else None
    return EnterpriseSessionSummary(
        id=session.id,
        chat_session_id=session.chat_session_id,
        customer=customer_payload(session),
        department=department_payload(session.department),
        status=session.status.value,
        intent=session.intent,
        confidence=session.confidence,
        last_message_preview=last_preview,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


def session_detail_payload(session: EnterpriseSession) -> EnterpriseSessionDetail:
    summary = session_summary_payload(session)
    return EnterpriseSessionDetail(
        **summary.model_dump(),
        messages=session.chat_session.messages if session.chat_session else [],
        handoff_package=session.handoff_package,
    )


@router.get("/overview", response_model=EnterpriseOverviewResponse)
def get_enterprise_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EnterpriseOverviewResponse:
    metrics = enterprise_metrics(db, current_user)
    departments = list_departments(db, current_user)
    tickets = list_enterprise_tickets(db, current_user)
    sessions = list_enterprise_sessions(db, current_user)
    organization = metrics["organization"]
    return EnterpriseOverviewResponse(
        metrics=EnterpriseMetricsResponse(
            organization=OrganizationResponse.model_validate(organization),
            total_tickets=metrics["total_tickets"],
            active_sessions=metrics["active_sessions"],
            escalations=metrics["escalations"],
            appointments=metrics["appointments"],
        ),
        departments=[DepartmentResponse.model_validate(item) for item in departments],
        tickets=[ticket_payload(item) for item in tickets],
        sessions=[session_summary_payload(item) for item in sessions],
    )


@router.get("/departments", response_model=list[DepartmentResponse])
def get_departments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[DepartmentResponse]:
    return [DepartmentResponse.model_validate(item) for item in list_departments(db, current_user)]


@router.get("/tickets", response_model=list[EnterpriseTicketResponse])
def get_tickets(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[EnterpriseTicketResponse]:
    return [ticket_payload(item) for item in list_enterprise_tickets(db, current_user)]


@router.patch("/tickets/{ticket_id}/status", response_model=EnterpriseTicketResponse)
def patch_ticket_status(
    ticket_id: int,
    payload: EnterpriseTicketStatusUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EnterpriseTicketResponse:
    ticket = update_enterprise_ticket_status(
        db,
        current_user=current_user,
        ticket_id=ticket_id,
        status_value=payload.status,
        resolution_note=payload.resolution_note,
    )
    return ticket_payload(ticket)


@router.get("/sessions", response_model=list[EnterpriseSessionSummary])
def get_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[EnterpriseSessionSummary]:
    return [session_summary_payload(item) for item in list_enterprise_sessions(db, current_user)]


@router.post("/sessions", response_model=EnterpriseSessionDetail)
def post_session(
    payload: EnterpriseSessionCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EnterpriseSessionDetail:
    session = create_enterprise_session(
        db,
        current_user=current_user,
        customer_name=payload.customer_name,
        customer_email=payload.customer_email,
        customer_phone=payload.customer_phone,
        channel=payload.channel,
    )
    return session_detail_payload(session)


@router.get("/sessions/{session_id}", response_model=EnterpriseSessionDetail)
def get_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EnterpriseSessionDetail:
    return session_detail_payload(get_enterprise_session(db, current_user, session_id))


@router.post("/sessions/{session_id}/messages", response_model=EnterpriseMessageResponse)
def post_message(
    session_id: int,
    payload: EnterpriseMessageRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EnterpriseMessageResponse:
    session, assistant_message, decision, ticket, appointment = process_enterprise_message(
        db,
        current_user=current_user,
        session_id=session_id,
        content=payload.content,
    )
    return EnterpriseMessageResponse(
        session=session_detail_payload(session),
        assistant_message=assistant_message,
        decision=EnterpriseDecisionResponse(
            intent=decision.intent,
            department=department_payload(decision.department),
            confidence=decision.confidence,
            action=decision.action,
            ticket=ticket_payload(ticket) if ticket else None,
            appointment=AppointmentResponse(**appointment_payload(appointment)) if appointment else None,
            handoff_package=session.handoff_package,
            explanation=decision.explanation,
        ),
    )
