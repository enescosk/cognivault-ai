from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.rate_limit import limiter

from app.api.dependencies import get_current_user, get_db
from app.models import IntelligenceJob, IntelligenceSource, Lead, OutreachDraft, OutreachDraftStatus, RoleName, User
from app.schemas.intelligence import (
    IntelligenceJobCreateRequest,
    IntelligenceJobResponse,
    IntelligenceSourceResponse,
    LeadResponse,
    OutreachDraftCreateRequest,
    OutreachDraftResponse,
)
from app.services.audit_service import log_action
from app.services.intelligence_service import (
    create_job,
    create_outreach_draft,
    ensure_intelligence_access,
    get_job,
    list_jobs,
    list_leads,
    list_sources,
)
from app.models import AuditResultStatus


router = APIRouter(prefix="/intelligence", tags=["intelligence"])


def source_payload(source: IntelligenceSource) -> IntelligenceSourceResponse:
    return IntelligenceSourceResponse.model_validate(source)


def lead_payload(lead: Lead) -> LeadResponse:
    return LeadResponse.model_validate(lead)


def job_payload(job: IntelligenceJob) -> IntelligenceJobResponse:
    return IntelligenceJobResponse.model_validate(job)


def draft_payload(draft: OutreachDraft) -> OutreachDraftResponse:
    return OutreachDraftResponse.model_validate(draft)


@router.get("/sources", response_model=list[IntelligenceSourceResponse])
def get_sources(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[IntelligenceSourceResponse]:
    return [source_payload(item) for item in list_sources(db, current_user)]


@router.get("/jobs", response_model=list[IntelligenceJobResponse])
def get_jobs(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[IntelligenceJobResponse]:
    return [job_payload(item) for item in list_jobs(db, current_user, limit)]


@router.post("/jobs", response_model=IntelligenceJobResponse)
@limiter.limit("10/minute")
def post_job(
    request: Request,
    payload: IntelligenceJobCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> IntelligenceJobResponse:
    job = create_job(
        db,
        current_user=current_user,
        source_kind=payload.source_kind,
        query=payload.query,
        target_location=payload.target_location,
        max_results=payload.max_results,
        seed_text=payload.seed_text,
    )
    return job_payload(job)


@router.get("/jobs/{job_id}", response_model=IntelligenceJobResponse)
def get_job_detail(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> IntelligenceJobResponse:
    return job_payload(get_job(db, current_user=current_user, job_id=job_id))


@router.get("/leads", response_model=list[LeadResponse])
def get_leads(
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[LeadResponse]:
    return [lead_payload(item) for item in list_leads(db, current_user, limit)]


@router.post("/outreach-drafts", response_model=OutreachDraftResponse)
def post_outreach_draft(
    payload: OutreachDraftCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OutreachDraftResponse:
    # legal_consent_acknowledged is validated at schema level; only reaches here if True
    draft = create_outreach_draft(
        db,
        current_user=current_user,
        lead_id=payload.lead_id,
        channel=payload.channel,
        intent=payload.intent,
        notes=payload.notes,
    )
    return draft_payload(draft)


@router.post("/outreach-drafts/{draft_id}/approve", response_model=OutreachDraftResponse)
def approve_outreach_draft(
    draft_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OutreachDraftResponse:
    """Admin-only: approve a draft for potential sending. Does NOT send the message."""
    if current_user.role.name != RoleName.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins can approve outreach drafts")
    draft = db.scalars(select(OutreachDraft).where(OutreachDraft.id == draft_id)).first()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft.status != OutreachDraftStatus.DRAFT:
        raise HTTPException(status_code=400, detail=f"Draft is already {draft.status}; cannot approve")
    draft.status = OutreachDraftStatus.APPROVED
    db.commit()
    db.refresh(draft)
    log_action(
        db,
        user_id=current_user.id,
        action_type="intelligence.outreach_draft_approved",
        explanation="Admin approved outreach draft; message still requires manual send",
        result_status=AuditResultStatus.SUCCESS,
        details={"draft_id": draft.id, "lead_id": draft.lead_id},
    )
    return draft_payload(draft)


@router.post("/outreach-drafts/{draft_id}/reject", response_model=OutreachDraftResponse)
def reject_outreach_draft(
    draft_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OutreachDraftResponse:
    """Operator or admin: reject a draft so it cannot be sent."""
    ensure_intelligence_access(current_user)
    draft = db.scalars(select(OutreachDraft).where(OutreachDraft.id == draft_id)).first()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft.status not in (OutreachDraftStatus.DRAFT, OutreachDraftStatus.APPROVED):
        raise HTTPException(status_code=400, detail=f"Draft in state {draft.status} cannot be rejected")
    draft.status = OutreachDraftStatus.REJECTED
    db.commit()
    db.refresh(draft)
    log_action(
        db,
        user_id=current_user.id,
        action_type="intelligence.outreach_draft_rejected",
        explanation="Outreach draft rejected; will not be sent",
        result_status=AuditResultStatus.INFO,
        details={"draft_id": draft.id, "lead_id": draft.lead_id},
    )
    return draft_payload(draft)
