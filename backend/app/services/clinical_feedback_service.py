from __future__ import annotations

from datetime import datetime, timezone
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.models import (
    Clinic,
    ClinicalModelFeedback,
    ClinicConversation,
    ClinicConversationStatus,
    ClinicMessage,
    ClinicMessageSender,
    ShadowReview,
    ShadowReviewStatus,
    User,
)
from app.services.agents import AgentType, DecisionRisk, build_decision, record_agent_decision


def update_shadow_review(
    db: Session,
    clinic: Clinic,
    current_user: User,
    review_id: int,
    status_value: str,
    final_reply: str | None,
    *,
    doctor_id: int | None = None,
) -> ShadowReview:
    """Apply a human verdict and atomically queue a privacy-gated training signal."""
    query = select(ShadowReview).where(ShadowReview.clinic_id == clinic.id, ShadowReview.id == review_id)
    if doctor_id is not None:
        query = query.where(ShadowReview.assigned_doctor_id == doctor_id)
    review = db.scalars(query).first()
    if review is None:
        raise NotFoundError("Shadow review not found")

    next_status = ShadowReviewStatus(status_value)
    if next_status == ShadowReviewStatus.EDITED and not final_reply:
        raise ValidationError("Edited review requires final_reply")

    review.status = next_status
    review.final_reply = final_reply or review.draft_reply
    review.reviewed_by_user_id = current_user.id
    review.reviewed_at = datetime.now(timezone.utc)

    feedback = _upsert_model_feedback(db, clinic, current_user, review, next_status)
    review.metadata_json = {
        **(review.metadata_json or {}),
        "model_feedback_id": feedback.id,
        "training_status": feedback.training_status,
    }

    conversation = db.scalars(
        select(ClinicConversation).where(
            ClinicConversation.clinic_id == clinic.id,
            ClinicConversation.id == review.conversation_id,
        )
    ).first()
    if conversation is None:
        raise NotFoundError("Clinical conversation not found")

    if next_status in {ShadowReviewStatus.APPROVED, ShadowReviewStatus.EDITED}:
        db.add(
            ClinicMessage(
                clinic_id=clinic.id,
                conversation_id=conversation.id,
                sender=ClinicMessageSender.OPERATOR,
                content=review.final_reply,
                language=conversation.language,
                intent=review.intent,
                confidence_score=review.confidence_score,
                metadata_json={"shadow_review_id": review.id, "delivery": "simulated"},
            )
        )
        conversation.status = ClinicConversationStatus.ACTIVE
    else:
        conversation.status = ClinicConversationStatus.WAITING_HUMAN

    db.add(review)
    db.add(conversation)
    db.commit()
    db.refresh(review)

    decision_intent = review.intent.value if hasattr(review.intent, "value") else str(review.intent)
    record_agent_decision(
        db,
        build_decision(
            agent_type=AgentType.ROUTING,
            intent=decision_intent,
            confidence=review.confidence_score,
            risk=DecisionRisk.HIGH if next_status == ShadowReviewStatus.REJECTED else DecisionRisk.MEDIUM,
            requires_human=True,
            action=f"shadow_review.{next_status.value}",
            reason="operator_review",
            organization_id=clinic.organization_id,
            payload={
                "review_id": review.id,
                "operator_user_id": current_user.id,
                "final_reply_used": review.final_reply,
                "model_feedback_id": feedback.id,
            },
        ),
        clinic_id=clinic.id,
        conversation_id=conversation.id,
        user_id=current_user.id,
    )
    return review


def _upsert_model_feedback(
    db: Session,
    clinic: Clinic,
    current_user: User,
    review: ShadowReview,
    outcome: ShadowReviewStatus,
) -> ClinicalModelFeedback:
    feedback = db.scalars(
        select(ClinicalModelFeedback).where(ClinicalModelFeedback.review_id == review.id)
    ).first()
    if feedback is None:
        feedback = ClinicalModelFeedback(
            clinic_id=clinic.id,
            conversation_id=review.conversation_id,
            review_id=review.id,
            patient_message_id=review.patient_message_id,
            reviewed_by_user_id=current_user.id,
            outcome=outcome.value,
            original_reply=review.draft_reply,
            training_status="pending_redaction",
        )
    corrected_reply = review.final_reply if outcome == ShadowReviewStatus.EDITED else None
    feedback.reviewed_by_user_id = current_user.id
    feedback.outcome = outcome.value
    feedback.corrected_reply = corrected_reply
    feedback.mismatch_json = build_reply_mismatch(review.draft_reply, corrected_reply)
    db.add(feedback)
    db.flush()
    return feedback


def build_reply_mismatch(original: str, corrected: str | None) -> dict:
    """Build bounded word-level deltas; never copy the patient transcript."""
    if corrected is None:
        return {"verdict": "rejected_or_accepted_without_edit", "segments": []}
    before = original.split()
    after = corrected.split()
    segments = []
    for operation, i1, i2, j1, j2 in SequenceMatcher(a=before, b=after).get_opcodes():
        if operation == "equal":
            continue
        segments.append(
            {
                "operation": operation,
                "model_text": " ".join(before[i1:i2])[:500],
                "human_text": " ".join(after[j1:j2])[:500],
            }
        )
    return {"verdict": "edited", "segments": segments[:40]}
