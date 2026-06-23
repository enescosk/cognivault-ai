from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.models import Clinic, ClinicConversation, ClinicPatient, PreIntake
from app.services.agents import AgentType, DecisionRisk, build_decision, record_agent_decision


def create_pre_intake(
    db: Session,
    clinic: Clinic,
    patient_id: int,
    conversation_id: int | None = None,
    answers: dict | None = None,
    is_complete: bool = False,
) -> PreIntake:
    patient = _get_patient(db, clinic, patient_id)
    if conversation_id is not None:
        conversation = db.scalars(
            select(ClinicConversation).where(
                ClinicConversation.id == conversation_id,
                ClinicConversation.clinic_id == clinic.id,
                ClinicConversation.patient_id == patient.id,
            )
        ).first()
        if conversation is None:
            raise ValidationError("Conversation does not belong to patient")

    pre_intake = PreIntake(
        clinic_id=clinic.id,
        patient_id=patient.id,
        conversation_id=conversation_id,
        answers_json=dict(answers or {}),
        is_complete=is_complete,
    )
    db.add(pre_intake)
    db.commit()
    db.refresh(pre_intake)
    return pre_intake


def get_pre_intake(db: Session, clinic: Clinic, pre_intake_id: int) -> PreIntake:
    pre_intake = db.scalars(
        select(PreIntake).where(PreIntake.id == pre_intake_id, PreIntake.clinic_id == clinic.id)
    ).first()
    if pre_intake is None:
        raise NotFoundError("Pre-intake not found")
    return pre_intake


def list_pre_intakes(
    db: Session,
    clinic: Clinic,
    patient_id: int | None = None,
    conversation_id: int | None = None,
    is_complete: bool | None = None,
    limit: int = 50,
) -> list[PreIntake]:
    stmt = select(PreIntake).where(PreIntake.clinic_id == clinic.id)
    if patient_id is not None:
        stmt = stmt.where(PreIntake.patient_id == patient_id)
    if conversation_id is not None:
        stmt = stmt.where(PreIntake.conversation_id == conversation_id)
    if is_complete is not None:
        stmt = stmt.where(PreIntake.is_complete == is_complete)
    return list(db.scalars(stmt.order_by(PreIntake.updated_at.desc()).limit(limit)))


def update_pre_intake(
    db: Session,
    clinic: Clinic,
    pre_intake_id: int,
    answers: dict | None = None,
    is_complete: bool | None = None,
    replace: bool = False,
) -> PreIntake:
    pre_intake = get_pre_intake(db, clinic, pre_intake_id)
    if answers is not None:
        if replace:
            pre_intake.answers_json = dict(answers)
        else:
            pre_intake.answers_json = {**(pre_intake.answers_json or {}), **answers}
    if is_complete is not None:
        pre_intake.is_complete = is_complete

    db.add(pre_intake)
    db.commit()
    db.refresh(pre_intake)
    record_agent_decision(
        db,
        build_decision(
            agent_type=AgentType.FORM,
            intent="pre_intake_progress",
            confidence=1.0 if pre_intake.is_complete else 0.5,
            risk=DecisionRisk.LOW,
            requires_human=False,
            action="persist_pre_intake" if pre_intake.is_complete else "ask_next_question",
            reason="form_complete" if pre_intake.is_complete else "form_in_progress",
            organization_id=clinic.organization_id,
            payload={
                "pre_intake_id": pre_intake.id,
                "answer_count": len(pre_intake.answers_json or {}),
                "is_complete": pre_intake.is_complete,
                "replace_mode": replace,
            },
        ),
        clinic_id=clinic.id,
        conversation_id=pre_intake.conversation_id,
    )
    return pre_intake


def _get_patient(db: Session, clinic: Clinic, patient_id: int) -> ClinicPatient:
    patient = db.scalars(
        select(ClinicPatient).where(ClinicPatient.id == patient_id, ClinicPatient.clinic_id == clinic.id)
    ).first()
    if patient is None:
        raise NotFoundError("Patient not found")
    return patient
