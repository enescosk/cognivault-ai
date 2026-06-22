from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.models import AuditResultStatus, RoleName, User
from app.services.audit_service import log_action
from app.services.quality_service import quality_report


router = APIRouter(prefix="/quality", tags=["quality"])


class QualityFeedbackRequest(BaseModel):
    scenario_id: str = Field(min_length=2, max_length=120)
    signal: str = Field(min_length=3, max_length=500)
    expected_behavior: str = Field(min_length=3, max_length=500)
    severity: str = Field(default="medium", pattern="^(low|medium|high|critical)$")


@router.get("/report")
def get_quality_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    return quality_report(db, current_user)


@router.post("/feedback")
def post_quality_feedback(
    payload: QualityFeedbackRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if current_user.role.name not in {RoleName.OPERATOR, RoleName.ADMIN}:
        return {"accepted": False, "reason": "Only operator or admin users can submit quality feedback."}

    log_action(
        db,
        user_id=current_user.id,
        action_type="quality.feedback_submitted",
        explanation="Quality feedback submitted for scenario improvement",
        result_status=AuditResultStatus.INFO,
        details=payload.model_dump(),
    )
    return {
        "accepted": True,
        "next_step": "Feedback was added to the audit trail and should be converted into a regression scenario.",
    }
