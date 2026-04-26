from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.config import get_settings
from app.models import (
    AuditResultStatus,
    IntelligenceJob,
    IntelligenceJobStatus,
    IntelligenceSource,
    IntelligenceSourceKind,
    Lead,
    LeadContactPoint,
    OutreachDraft,
    RoleName,
    User,
)
from app.services.audit_service import log_action
from app.services.intelligence_connectors import get_connector


def ensure_intelligence_access(user: User) -> None:
    if user.role.name not in {RoleName.OPERATOR, RoleName.ADMIN}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")


def seed_intelligence_sources(db: Session) -> None:
    settings = get_settings()
    defaults = [
        (
            "Manual Paste / User Provided Text",
            IntelligenceSourceKind.MANUAL,
            None,
            False,
            {"collection": "Only parses text provided by an authenticated user."},
        ),
        (
            "Curated Public Websites",
            IntelligenceSourceKind.WEBSITE,
            None,
            False,
            {"collection": "Use approved public company/contact pages with provenance."},
        ),
        (
            "Google Places",
            IntelligenceSourceKind.GOOGLE_PLACES,
            "https://developers.google.com/maps/documentation/places/web-service",
            True,
            {"collection": "Use official Places API. Store public business listings only."},
        ),
        (
            "X API",
            IntelligenceSourceKind.X_API,
            "https://developer.x.com/",
            True,
            {"collection": "Use official API/OAuth. Do not bypass login, paywalls, or rate limits."},
        ),
        (
            "Reddit API",
            IntelligenceSourceKind.REDDIT_API,
            "https://www.reddit.com/dev/api/",
            True,
            {"collection": "Use official API/OAuth. Do not collect private or sensitive user data."},
        ),
    ]
    for name, kind, base_url, requires_api_key, policy in defaults:
        existing = db.scalars(select(IntelligenceSource).where(IntelligenceSource.kind == kind)).first()
        if existing:
            continue
        db.add(
            IntelligenceSource(
                name=name,
                kind=kind,
                base_url=base_url,
                requires_api_key=requires_api_key,
                rate_limit_per_minute=settings.intelligence_default_rate_limit_per_minute,
                policy=policy,
            )
        )
    db.commit()


def _persist_connector_leads(
    db: Session,
    *,
    job: IntelligenceJob,
    connector_leads,
) -> int:
    lead_count = 0
    for item in connector_leads[: job.max_results]:
        lead = Lead(
            job_id=job.id,
            organization_name=item.organization_name,
            description=item.description,
            location=item.location,
            source_url=item.source_url,
            source_kind=item.source_kind,
            confidence=item.confidence,
            consent_basis=item.consent_basis,
            provenance=item.provenance,
        )
        db.add(lead)
        db.flush()
        for index, contact in enumerate(item.contacts):
            db.add(
                LeadContactPoint(
                    lead_id=lead.id,
                    kind=contact.kind,
                    value=contact.value,
                    normalized_value=contact.normalized_value,
                    is_primary=index == 0,
                    confidence=contact.confidence,
                    source_url=item.source_url,
                )
            )
        lead_count += 1
    return lead_count


def _job_has_actionable_contact(job: IntelligenceJob) -> bool:
    return any(lead.contact_points for lead in job.leads)


def _run_connector_job(
    db: Session,
    *,
    current_user: User,
    kind: IntelligenceSourceKind,
    query: str,
    target_location: str | None,
    max_results: int,
    metadata_json: dict,
) -> IntelligenceJob:
    _check_source_allowed(kind)
    source = db.scalars(select(IntelligenceSource).where(IntelligenceSource.kind == kind)).first()
    if not source or not source.is_active:
        raise HTTPException(status_code=400, detail=f"{kind.value} intelligence source is not active")

    job = IntelligenceJob(
        source_id=source.id,
        requested_by_user_id=current_user.id,
        query=query.strip(),
        target_location=target_location.strip() if target_location else None,
        max_results=max_results,
        metadata_json=metadata_json,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    connector = get_connector(kind)
    if connector is None:
        job.status = IntelligenceJobStatus.BLOCKED
        job.error_message = f"No connector registered for {kind.value}"
        db.commit()
        return get_job(db, current_user=current_user, job_id=job.id)

    job.status = IntelligenceJobStatus.RUNNING
    db.commit()
    connector_leads = connector.discover(
        query=job.query,
        target_location=job.target_location,
        max_results=job.max_results,
    )
    lead_count = _persist_connector_leads(db, job=job, connector_leads=connector_leads)
    job.status = IntelligenceJobStatus.COMPLETED
    job.summary = f"{lead_count} lead candidate(s) discovered"
    db.commit()
    return get_job(db, current_user=current_user, job_id=job.id)


def list_sources(db: Session, current_user: User) -> list[IntelligenceSource]:
    ensure_intelligence_access(current_user)
    seed_intelligence_sources(db)
    return list(db.scalars(select(IntelligenceSource).order_by(IntelligenceSource.name)))


def _source_kind(value: str) -> IntelligenceSourceKind:
    try:
        return IntelligenceSourceKind(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Unsupported source kind: {value}") from exc


def _check_source_allowed(kind: IntelligenceSourceKind) -> None:
    settings = get_settings()
    if kind.value not in settings.intelligence_allowed_source_list:
        raise HTTPException(status_code=400, detail=f"Source kind is not allowed by policy: {kind.value}")


def create_job(
    db: Session,
    *,
    current_user: User,
    source_kind: str,
    query: str,
    target_location: str | None,
    max_results: int,
    seed_text: str | None = None,
) -> IntelligenceJob:
    ensure_intelligence_access(current_user)
    seed_intelligence_sources(db)
    kind = _source_kind(source_kind)
    _check_source_allowed(kind)
    source = db.scalars(select(IntelligenceSource).where(IntelligenceSource.kind == kind)).first()
    if not source or not source.is_active:
        raise HTTPException(status_code=400, detail="Source is not active")

    job = IntelligenceJob(
        source_id=source.id,
        requested_by_user_id=current_user.id,
        query=query.strip(),
        target_location=target_location.strip() if target_location else None,
        max_results=max_results,
        metadata_json={"seed_text_supplied": bool(seed_text)},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    run_job(db, current_user=current_user, job_id=job.id, seed_text=seed_text)
    return get_job(db, current_user=current_user, job_id=job.id)


def run_job(db: Session, *, current_user: User, job_id: int, seed_text: str | None = None) -> IntelligenceJob:
    ensure_intelligence_access(current_user)
    job = db.get(IntelligenceJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    connector = get_connector(job.source.kind)
    if connector is None:
        job.status = IntelligenceJobStatus.BLOCKED
        job.error_message = "No connector registered for this source kind"
        db.commit()
        return job

    job.status = IntelligenceJobStatus.RUNNING
    db.commit()
    try:
        connector_leads = connector.discover(
            query=job.query,
            target_location=job.target_location,
            max_results=job.max_results,
            seed_text=seed_text,
        )
        _persist_connector_leads(db, job=job, connector_leads=connector_leads)
        job.status = IntelligenceJobStatus.COMPLETED
        job.summary = f"{len(connector_leads[: job.max_results])} lead candidate(s) discovered"
        log_action(
            db,
            user_id=current_user.id,
            action_type="intelligence.job_completed",
            explanation="Intelligence discovery job completed",
            result_status=AuditResultStatus.SUCCESS,
            details={"job_id": job.id, "source_kind": job.source.kind.value, "lead_count": len(connector_leads)},
        )
    except Exception as exc:  # noqa: BLE001
        job.status = IntelligenceJobStatus.FAILED
        job.error_message = str(exc)[:500]
        log_action(
            db,
            user_id=current_user.id,
            action_type="intelligence.job_failed",
            explanation="Intelligence discovery job failed",
            success=False,
            result_status=AuditResultStatus.FAILURE,
            details={"job_id": job.id, "error": job.error_message},
        )
    db.commit()
    return job


def discover_company_contact_for_agent(
    db: Session,
    *,
    current_user: User,
    query: str,
    target_location: str | None = None,
) -> IntelligenceJob:
    seed_intelligence_sources(db)
    website_job = _run_connector_job(
        db,
        current_user=current_user,
        kind=IntelligenceSourceKind.WEBSITE,
        query=query,
        target_location=target_location,
        max_results=3,
        metadata_json={"trigger": "agent_external_outreach", "resolver_step": "curated_website"},
    )
    if _job_has_actionable_contact(website_job):
        log_action(
            db,
            user_id=current_user.id,
            action_type="intelligence.agent_company_contact_found",
            explanation="Agent discovered public company contact details from curated sources",
            result_status=AuditResultStatus.SUCCESS,
            details={"job_id": website_job.id, "query": website_job.query, "source_kind": "website"},
        )
        db.commit()
        return website_job

    google_job = _run_connector_job(
        db,
        current_user=current_user,
        kind=IntelligenceSourceKind.GOOGLE_PLACES,
        query=query,
        target_location=target_location,
        max_results=5,
        metadata_json={
            "trigger": "agent_external_outreach",
            "resolver_step": "google_places",
            "fallback_from_job_id": website_job.id,
        },
    )
    log_action(
        db,
        user_id=current_user.id,
        action_type="intelligence.agent_company_contact_found",
        explanation="Agent resolved company/place contact details through Google Places fallback",
        result_status=AuditResultStatus.SUCCESS if _job_has_actionable_contact(google_job) else AuditResultStatus.INFO,
        details={"job_id": google_job.id, "query": google_job.query, "source_kind": "google_places"},
    )
    db.commit()
    return google_job


def list_jobs(db: Session, current_user: User, limit: int = 50) -> list[IntelligenceJob]:
    ensure_intelligence_access(current_user)
    return list(
        db.scalars(
            select(IntelligenceJob)
            .options(joinedload(IntelligenceJob.source), selectinload(IntelligenceJob.leads).selectinload(Lead.contact_points))
            .order_by(IntelligenceJob.created_at.desc())
            .limit(limit)
        )
    )


def get_job(db: Session, *, current_user: User, job_id: int) -> IntelligenceJob:
    job = db.scalars(
        select(IntelligenceJob)
        .options(joinedload(IntelligenceJob.source), selectinload(IntelligenceJob.leads).selectinload(Lead.contact_points))
        .where(IntelligenceJob.id == job_id)
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if current_user.role.name not in {RoleName.OPERATOR, RoleName.ADMIN} and job.requested_by_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return job


def list_leads(db: Session, current_user: User, limit: int = 100) -> list[Lead]:
    ensure_intelligence_access(current_user)
    return list(
        db.scalars(
            select(Lead)
            .options(selectinload(Lead.contact_points))
            .order_by(Lead.created_at.desc())
            .limit(limit)
        )
    )


def create_outreach_draft(
    db: Session,
    *,
    current_user: User,
    lead_id: int,
    channel: str,
    intent: str,
    notes: str | None = None,
) -> OutreachDraft:
    ensure_intelligence_access(current_user)
    lead = db.scalars(select(Lead).options(selectinload(Lead.contact_points)).where(Lead.id == lead_id)).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    primary_contact = next((item for item in lead.contact_points if item.is_primary), None)
    subject = f"Cognivault AI - {intent}" if channel == "email" else None
    body = (
        f"Merhaba, {lead.organization_name} ile ilgili iletisim kurmak istiyoruz. "
        f"Kaynak: {lead.source_kind.value}. "
        "Bu mesaj taslaktir; gonderim icin operator onayi gerekir."
    )
    if primary_contact:
        body += f" Birincil iletisim noktasi: {primary_contact.value}."
    if notes:
        body += f" Not: {notes.strip()}"
    draft = OutreachDraft(
        lead_id=lead.id,
        created_by_user_id=current_user.id,
        channel=channel,
        subject=subject,
        body=body,
        metadata_json={"intent": intent, "requires_human_approval": True},
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    log_action(
        db,
        user_id=current_user.id,
        action_type="intelligence.outreach_draft_created",
        explanation="Outreach draft created; no message was sent",
        result_status=AuditResultStatus.INFO,
        details={"lead_id": lead.id, "draft_id": draft.id, "channel": channel},
    )
    return draft
