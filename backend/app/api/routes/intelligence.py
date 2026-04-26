from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.models import IntelligenceJob, IntelligenceSource, Lead, OutreachDraft, User
from app.schemas.intelligence import (
    IntelligenceJobCreateRequest,
    IntelligenceJobResponse,
    IntelligenceSourceResponse,
    LeadResponse,
    OutreachDraftCreateRequest,
    OutreachDraftResponse,
)
from app.services.intelligence_service import (
    create_job,
    create_outreach_draft,
    get_job,
    list_jobs,
    list_leads,
    list_sources,
)


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
def post_job(
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
    draft = create_outreach_draft(
        db,
        current_user=current_user,
        lead_id=payload.lead_id,
        channel=payload.channel,
        intent=payload.intent,
        notes=payload.notes,
    )
    return draft_payload(draft)
