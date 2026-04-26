from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Appointment,
    AuditResultStatus,
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
    RoleName,
    RoutingRule,
    User,
)
from app.services.appointment_service import appointment_payload, check_available_slots, create_appointment, normalize_department
from app.services.audit_service import log_action
from app.services.chat_service import add_message


GENERAL_DEPARTMENT = "General Support"


@dataclass
class RoutingDecision:
    intent: str
    department: Department | None
    confidence: int
    action: str
    explanation: str
    extracted_fields: dict
    needs_handoff: bool = False


def ensure_enterprise_access(user: User) -> None:
    if user.role.name not in {RoleName.OPERATOR, RoleName.ADMIN}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Enterprise mode requires operator or admin role")


def get_default_organization(db: Session) -> Organization:
    organization = db.scalars(select(Organization).order_by(Organization.id)).first()
    if organization is None:
        organization = Organization(name="Cognivault Enterprise Demo", domain="cognivault.local")
        db.add(organization)
        db.commit()
        db.refresh(organization)
    return organization


def _department_by_name(db: Session, organization_id: int, name: str) -> Department | None:
    return db.scalars(
        select(Department).where(
            Department.organization_id == organization_id,
            func.lower(Department.name) == name.lower(),
            Department.is_active.is_(True),
        )
    ).first()


def _extract_phone(text: str) -> str | None:
    match = re.search(r"(\+?\d[\d\s()-]{8,}\d)", text)
    return match.group(1).strip() if match else None


def _extract_email(text: str) -> str | None:
    match = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    return match.group(0) if match else None


def _last_messages(session: EnterpriseSession, limit: int = 6) -> list[dict]:
    messages = session.chat_session.messages[-limit:] if session.chat_session and session.chat_session.messages else []
    return [{"sender": item.sender.value, "content": item.content, "created_at": item.created_at.isoformat()} for item in messages]


def build_handoff_package(session: EnterpriseSession, decision: RoutingDecision, user_message: str) -> dict:
    return {
        "summary": decision.explanation,
        "intent": decision.intent,
        "extracted_fields": decision.extracted_fields,
        "suggested_department": decision.department.name if decision.department else GENERAL_DEPARTMENT,
        "confidence": decision.confidence,
        "last_messages": _last_messages(session),
        "latest_customer_message": user_message,
    }


def analyze_customer_signal(content: str, decision: RoutingDecision) -> dict:
    text = content.lower()
    negative_terms = ["acil", "urgent", "çalışmıyor", "calismiyor", "hata", "error", "şikayet", "sikayet", "kızgın", "angry"]
    positive_terms = ["teşekkür", "tesekkur", "thanks", "great", "harika", "memnun"]
    risk_terms = ["manager", "iptal", "cancel", "yasal", "legal", "ceza", "penalty", "down", "blocked", "kritik", "critical"]

    negative_hits = [term for term in negative_terms if term in text]
    positive_hits = [term for term in positive_terms if term in text]
    risk_hits = [term for term in risk_terms if term in text]

    if negative_hits and not positive_hits:
        sentiment = "negative"
    elif positive_hits and not negative_hits:
        sentiment = "positive"
    else:
        sentiment = "neutral"

    if decision.needs_handoff or decision.action == "escalate" or len(risk_hits) >= 2:
        risk = "high"
    elif negative_hits or risk_hits or decision.confidence < 65:
        risk = "medium"
    else:
        risk = "low"

    suggested_next_action = {
        "high": "Assign a human owner, confirm impact, and send an SLA update.",
        "medium": "Confirm missing details and keep the ticket visible in the queue.",
        "low": "Continue self-service or normal queue handling.",
    }[risk]

    return {
        "sentiment": sentiment,
        "risk": risk,
        "signals": negative_hits + risk_hits + positive_hits,
        "summary": decision.explanation,
        "suggested_next_action": suggested_next_action,
    }


def _knowledge_suggestions_for_message(db: Session, current_user: User, content: str) -> list[dict]:
    try:
        from app.services.knowledge_service import search_knowledge_articles

        return [
            {
                "id": article.id,
                "title": article.title,
                "content": article.content[:220],
                "tags": article.tags,
                "score": score,
            }
            for article, score in search_knowledge_articles(db, current_user, content, limit=3)
        ]
    except Exception:
        return []


def route_enterprise_request(db: Session, organization: Organization, content: str) -> RoutingDecision:
    text = content.lower()
    rules = list(
        db.scalars(
            select(RoutingRule)
            .options(selectinload(RoutingRule.department))
            .where(RoutingRule.organization_id == organization.id, RoutingRule.is_active.is_(True))
        )
    )

    best_rule: RoutingRule | None = None
    best_score = 0
    matched_keywords: list[str] = []

    for rule in rules:
        keywords = [kw.lower() for kw in (rule.keywords or [])]
        hits = [kw for kw in keywords if kw in text]
        if not hits:
            continue
        score = min(98, rule.confidence_boost + (len(hits) * 6))
        if score > best_score:
            best_score = score
            best_rule = rule
            matched_keywords = hits

    escalation_terms = ["insan", "temsilci", "agent", "şikayet", "sikayet", "acil", "urgent", "manager", "escalate"]
    greeting_terms = ["merhaba", "selam", "hello", "hi", "iyi günler"]
    needs_handoff = any(term in text for term in escalation_terms)

    if best_rule is None:
        department = _department_by_name(db, organization.id, GENERAL_DEPARTMENT)
        if any(term in text for term in greeting_terms) and len(text.split()) <= 5:
            return RoutingDecision(
                intent="general_greeting",
                department=department,
                confidence=74,
                action="self_service",
                explanation="Greeting detected; AI can continue intake without creating a case yet.",
                extracted_fields={},
            )
        return RoutingDecision(
            intent="general_support",
            department=department,
            confidence=52,
            action="create_ticket",
            explanation="No high-confidence rule matched; routed to General Support.",
            extracted_fields={"matched_keywords": []},
            needs_handoff=True,
        )

    action = "schedule_appointment" if best_rule.intent == "appointment_request" else "create_ticket"
    if needs_handoff:
        action = "escalate"

    extracted = {
        "matched_keywords": matched_keywords,
        "phone": _extract_phone(content),
        "email": _extract_email(content),
    }
    return RoutingDecision(
        intent=best_rule.intent,
        department=best_rule.department,
        confidence=best_score,
        action=action,
        explanation=f"Matched {best_rule.intent} via {', '.join(matched_keywords)}.",
        extracted_fields={key: value for key, value in extracted.items() if value},
        needs_handoff=needs_handoff,
    )


def create_enterprise_session(
    db: Session,
    *,
    current_user: User,
    customer_name: str,
    customer_email: str | None,
    customer_phone: str | None,
    channel: str,
) -> EnterpriseSession:
    ensure_enterprise_access(current_user)
    organization = get_default_organization(db)
    customer = EnterpriseCustomer(
        organization_id=organization.id,
        full_name=customer_name.strip(),
        email=customer_email,
        phone=customer_phone,
        external_ref=f"CALL-{organization.id}-{current_user.id}",
    )
    chat_session = ChatSession(
        user_id=current_user.id,
        title=f"Enterprise intake - {customer_name.strip()}",
        workflow_state={"mode": "enterprise", "channel": channel},
    )
    db.add(customer)
    db.add(chat_session)
    db.commit()
    db.refresh(customer)
    db.refresh(chat_session)

    session = EnterpriseSession(
        organization_id=organization.id,
        customer_id=customer.id,
        chat_session_id=chat_session.id,
        channel=channel,
        status=EnterpriseSessionStatus.ACTIVE,
        metadata_json={"created_by_user_id": current_user.id},
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    log_action(
        db,
        user_id=current_user.id,
        session_id=chat_session.id,
        action_type="enterprise.session_created",
        explanation="Enterprise intake session created",
        result_status=AuditResultStatus.SUCCESS,
        details={"enterprise_session_id": session.id, "customer_id": customer.id, "channel": channel},
    )
    return get_enterprise_session(db, current_user, session.id)


def list_enterprise_sessions(db: Session, current_user: User) -> list[EnterpriseSession]:
    ensure_enterprise_access(current_user)
    return list(
        db.scalars(
            select(EnterpriseSession)
            .options(
                selectinload(EnterpriseSession.customer),
                selectinload(EnterpriseSession.department),
                selectinload(EnterpriseSession.chat_session).selectinload(ChatSession.messages),
            )
            .order_by(EnterpriseSession.updated_at.desc())
        )
    )


def get_enterprise_session(db: Session, current_user: User, session_id: int) -> EnterpriseSession:
    ensure_enterprise_access(current_user)
    session = db.scalars(
        select(EnterpriseSession)
        .options(
            selectinload(EnterpriseSession.customer),
            selectinload(EnterpriseSession.department),
            selectinload(EnterpriseSession.chat_session).selectinload(ChatSession.messages),
        )
        .where(EnterpriseSession.id == session_id)
    ).first()
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enterprise session not found")
    return session


def list_departments(db: Session, current_user: User) -> list[Department]:
    ensure_enterprise_access(current_user)
    organization = get_default_organization(db)
    return list(db.scalars(select(Department).where(Department.organization_id == organization.id).order_by(Department.name)))


def list_enterprise_tickets(db: Session, current_user: User) -> list[EnterpriseTicket]:
    ensure_enterprise_access(current_user)
    return list(
        db.scalars(
            select(EnterpriseTicket)
            .options(
                selectinload(EnterpriseTicket.customer),
                selectinload(EnterpriseTicket.department),
                selectinload(EnterpriseTicket.assigned_agent),
            )
            .order_by(EnterpriseTicket.created_at.desc())
        )
    )


def list_enterprise_agents(db: Session, current_user: User) -> list[EnterpriseAgent]:
    ensure_enterprise_access(current_user)
    organization = get_default_organization(db)
    return list(
        db.scalars(
            select(EnterpriseAgent)
            .where(EnterpriseAgent.organization_id == organization.id)
            .order_by(EnterpriseAgent.display_name.asc())
        )
    )


def update_enterprise_ticket(
    db: Session,
    *,
    current_user: User,
    ticket_id: int,
    status_value: str | None = None,
    priority: str | None = None,
    assigned_agent_id: int | None = None,
    assigned_agent_id_provided: bool = False,
    resolution_note: str | None = None,
) -> EnterpriseTicket:
    ensure_enterprise_access(current_user)
    ticket = db.scalars(
        select(EnterpriseTicket)
        .options(
            selectinload(EnterpriseTicket.customer),
            selectinload(EnterpriseTicket.department),
            selectinload(EnterpriseTicket.session),
            selectinload(EnterpriseTicket.assigned_agent),
        )
        .where(EnterpriseTicket.id == ticket_id)
    ).first()
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enterprise ticket not found")

    next_status = ticket.status
    if status_value:
        try:
            next_status = EnterpriseTicketStatus(status_value)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported ticket status") from exc
        ticket.status = next_status
        if next_status == EnterpriseTicketStatus.ESCALATED and priority is None:
            ticket.priority = "high"
        elif next_status == EnterpriseTicketStatus.CLOSED and priority is None:
            ticket.priority = "normal"

    if priority is not None:
        ticket.priority = priority

    if assigned_agent_id_provided and assigned_agent_id is None:
        ticket.assigned_agent_id = None
    elif assigned_agent_id is not None:
        agent = db.get(EnterpriseAgent, assigned_agent_id)
        if agent is None or agent.organization_id != ticket.organization_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Assigned agent is not available")
        ticket.assigned_agent_id = agent.id

    notes = dict(ticket.handoff_package or {})
    history = list(notes.get("status_history") or [])
    history.append(
        {
            "status": next_status.value,
            "priority": ticket.priority,
            "assigned_agent_id": ticket.assigned_agent_id,
            "updated_by_user_id": current_user.id,
            "note": resolution_note,
        }
    )
    notes["status_history"] = history
    if resolution_note:
        notes["latest_resolution_note"] = resolution_note
    ticket.handoff_package = notes

    if ticket.session is not None:
        if next_status == EnterpriseTicketStatus.CLOSED:
            ticket.session.status = EnterpriseSessionStatus.CLOSED
        elif next_status == EnterpriseTicketStatus.ESCALATED:
            ticket.session.status = EnterpriseSessionStatus.NEEDS_HUMAN
        else:
            ticket.session.status = EnterpriseSessionStatus.ACTIVE
        db.add(ticket.session)

    db.add(ticket)
    db.commit()
    db.refresh(ticket)

    log_action(
        db,
        user_id=current_user.id,
        session_id=ticket.session.chat_session_id if ticket.session else None,
        action_type="enterprise.ticket_status_updated",
        explanation=f"Enterprise ticket updated as {next_status.value}",
        result_status=AuditResultStatus.SUCCESS,
        details={
            "ticket_id": ticket.id,
            "status": next_status.value,
            "priority": ticket.priority,
            "assigned_agent_id": ticket.assigned_agent_id,
            "resolution_note": resolution_note,
        },
    )
    return ticket


def update_enterprise_ticket_status(
    db: Session,
    *,
    current_user: User,
    ticket_id: int,
    status_value: str,
    resolution_note: str | None = None,
) -> EnterpriseTicket:
    return update_enterprise_ticket(
        db,
        current_user=current_user,
        ticket_id=ticket_id,
        status_value=status_value,
        resolution_note=resolution_note,
    )


def _create_ticket(
    db: Session,
    *,
    session: EnterpriseSession,
    decision: RoutingDecision,
    user_message: str,
    handoff_package: dict,
) -> EnterpriseTicket:
    ticket = EnterpriseTicket(
        organization_id=session.organization_id,
        customer_id=session.customer_id,
        session_id=session.id,
        department_id=decision.department.id if decision.department else None,
        intent=decision.intent,
        description=user_message.strip(),
        status=EnterpriseTicketStatus.ESCALATED if decision.action == "escalate" else EnterpriseTicketStatus.OPEN,
        priority="high" if decision.action == "escalate" else "normal",
        confidence=decision.confidence,
        handoff_package=handoff_package,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


def _schedule_enterprise_appointment(
    db: Session,
    *,
    current_user: User,
    session: EnterpriseSession,
    decision: RoutingDecision,
    user_message: str,
) -> Appointment | None:
    phone = decision.extracted_fields.get("phone") or session.customer.phone or current_user.phone
    if not phone:
        return None

    department_hint = normalize_department(user_message) or "Onboarding Desk"
    slots = check_available_slots(db, department=department_hint, limit=1)
    if not slots and department_hint != "Onboarding Desk":
        slots = check_available_slots(db, department="Onboarding Desk", limit=1)
    if not slots:
        return None

    appointment = create_appointment(
        db,
        acting_user=current_user,
        slot_id=slots[0].id,
        purpose=user_message.strip(),
        contact_phone=phone,
        notes=f"Enterprise session #{session.id} for {session.customer.full_name}",
        language=current_user.locale,
        target_user_id=current_user.id,
    )
    return appointment


def process_enterprise_message(
    db: Session,
    *,
    current_user: User,
    session_id: int,
    content: str,
) -> tuple[EnterpriseSession, str, RoutingDecision, EnterpriseTicket | None, Appointment | None]:
    session = get_enterprise_session(db, current_user, session_id)
    organization = get_default_organization(db)

    add_message(
        db,
        session=session.chat_session,
        sender=MessageSender.USER,
        content=content,
        language=current_user.locale,
        metadata_json={"mode": "enterprise", "customer_id": session.customer_id},
    )

    decision = route_enterprise_request(db, organization, content)
    handoff_package = (
        build_handoff_package(session, decision, content)
        if decision.needs_handoff or decision.action in {"create_ticket", "escalate", "schedule_appointment"}
        else {}
    )
    copilot_insights = analyze_customer_signal(content, decision)
    knowledge_suggestions = _knowledge_suggestions_for_message(db, current_user, content)
    if handoff_package:
        handoff_package["copilot_insights"] = copilot_insights
        handoff_package["knowledge_suggestions"] = knowledge_suggestions

    ticket: EnterpriseTicket | None = None
    appointment: Appointment | None = None

    session.intent = decision.intent
    session.confidence = decision.confidence
    session.department_id = decision.department.id if decision.department else None

    if decision.action == "self_service":
        assistant_message = (
            "Merhaba, Enterprise intake modundayım. Talebi yazın; niyeti, departmanı ve gerekiyorsa ticket/eskalasyon adımını kaydedeceğim."
            if current_user.locale == "tr"
            else "Hello, Enterprise intake mode is ready. Share the request and I will route it, create a ticket, or prepare escalation when needed."
        )
    elif decision.action == "schedule_appointment":
        appointment = _schedule_enterprise_appointment(
            db,
            current_user=current_user,
            session=session,
            decision=decision,
            user_message=content,
        )
        if appointment is None:
            ticket = _create_ticket(db, session=session, decision=decision, user_message=content, handoff_package=handoff_package)
            session.handoff_package = handoff_package
            assistant_message = (
                "Randevu talebini algıladım ancak randevuyu tamamlamak için telefon/uygun slot eksik. Talep için ticket oluşturdum."
                if current_user.locale == "tr"
                else "I detected an appointment request, but phone or slot data is missing. I created a ticket for follow-up."
            )
        else:
            assistant_message = (
                f"Randevu oluşturuldu. Onay kodu {appointment.confirmation_code}; departman {appointment.department}."
                if current_user.locale == "tr"
                else f"Appointment created. Confirmation code {appointment.confirmation_code}; department {appointment.department}."
            )
    else:
        ticket = _create_ticket(db, session=session, decision=decision, user_message=content, handoff_package=handoff_package)
        session.handoff_package = handoff_package
        if decision.action == "escalate":
            session.status = EnterpriseSessionStatus.NEEDS_HUMAN
            assistant_message = (
                f"Talep {decision.department.name if decision.department else GENERAL_DEPARTMENT} ekibine eskale edildi. İnsan temsilci için handoff paketi hazırlandı."
                if current_user.locale == "tr"
                else f"The request was escalated to {decision.department.name if decision.department else GENERAL_DEPARTMENT}. A human handoff package is ready."
            )
        else:
            assistant_message = (
                f"Talep {decision.department.name if decision.department else GENERAL_DEPARTMENT} ekibine yönlendirildi ve ticket açıldı."
                if current_user.locale == "tr"
                else f"The request was routed to {decision.department.name if decision.department else GENERAL_DEPARTMENT} and a ticket was opened."
            )

    db.add(session)
    db.commit()
    db.refresh(session)

    add_message(
        db,
        session=session.chat_session,
        sender=MessageSender.ASSISTANT,
        content=assistant_message,
        language=current_user.locale,
        metadata_json={
            "mode": "enterprise",
            "intent": decision.intent,
            "action": decision.action,
            "confidence": decision.confidence,
            "ticket_id": ticket.id if ticket else None,
            "appointment_id": appointment.id if appointment else None,
        },
    )

    action_type = {
        "self_service": "enterprise.self_service",
        "create_ticket": "enterprise.ticket_created",
        "schedule_appointment": "enterprise.appointment_created" if appointment else "enterprise.ticket_created",
        "escalate": "enterprise.escalated",
    }.get(decision.action, "enterprise.routed")
    log_action(
        db,
        user_id=current_user.id,
        session_id=session.chat_session_id,
        action_type=action_type,
        explanation=decision.explanation,
        result_status=AuditResultStatus.SUCCESS,
        details={
            "enterprise_session_id": session.id,
            "intent": decision.intent,
            "department": decision.department.name if decision.department else None,
            "confidence": decision.confidence,
            "ticket_id": ticket.id if ticket else None,
            "appointment_id": appointment.id if appointment else None,
        },
    )

    return get_enterprise_session(db, current_user, session.id), assistant_message, decision, ticket, appointment


def enterprise_metrics(db: Session, current_user: User) -> dict:
    ensure_enterprise_access(current_user)
    organization = get_default_organization(db)
    total_tickets = db.scalar(select(func.count(EnterpriseTicket.id)).where(EnterpriseTicket.organization_id == organization.id)) or 0
    open_tickets = (
        db.scalar(
            select(func.count(EnterpriseTicket.id)).where(
                EnterpriseTicket.organization_id == organization.id,
                EnterpriseTicket.status.in_(
                    [
                        EnterpriseTicketStatus.OPEN,
                        EnterpriseTicketStatus.IN_PROGRESS,
                        EnterpriseTicketStatus.ESCALATED,
                    ]
                ),
            )
        )
        or 0
    )
    high_priority_tickets = (
        db.scalar(
            select(func.count(EnterpriseTicket.id)).where(
                EnterpriseTicket.organization_id == organization.id,
                EnterpriseTicket.priority.in_(["high", "urgent"]),
                EnterpriseTicket.status != EnterpriseTicketStatus.CLOSED,
            )
        )
        or 0
    )
    active_sessions = (
        db.scalar(
            select(func.count(EnterpriseSession.id)).where(
                EnterpriseSession.organization_id == organization.id,
                EnterpriseSession.status.in_([EnterpriseSessionStatus.ACTIVE, EnterpriseSessionStatus.NEEDS_HUMAN]),
            )
        )
        or 0
    )
    escalations = (
        db.scalar(
            select(func.count(EnterpriseSession.id)).where(
                EnterpriseSession.organization_id == organization.id,
                EnterpriseSession.status == EnterpriseSessionStatus.NEEDS_HUMAN,
            )
        )
        or 0
    )
    appointments = db.scalar(select(func.count(Appointment.id))) or 0
    ticket_rows = list(
        db.scalars(
            select(EnterpriseTicket).where(
                EnterpriseTicket.organization_id == organization.id,
                EnterpriseTicket.status != EnterpriseTicketStatus.CLOSED,
            )
        )
    )
    now = datetime.now(timezone.utc)
    sla_limits = {"urgent": 2, "high": 4, "normal": 24, "low": 72}
    sla_breached = 0
    for ticket in ticket_rows:
        created_at = ticket.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        elapsed_hours = (now - created_at).total_seconds() / 3600
        if elapsed_hours >= sla_limits.get(ticket.priority, 24):
            sla_breached += 1
    avg_confidence_value = db.scalar(
        select(func.avg(EnterpriseTicket.confidence)).where(EnterpriseTicket.organization_id == organization.id)
    )
    return {
        "organization": organization,
        "total_tickets": total_tickets,
        "open_tickets": open_tickets,
        "high_priority_tickets": high_priority_tickets,
        "sla_breached": sla_breached,
        "avg_confidence": round(float(avg_confidence_value or 0), 1),
        "active_sessions": active_sessions,
        "escalations": escalations,
        "appointments": appointments,
    }
