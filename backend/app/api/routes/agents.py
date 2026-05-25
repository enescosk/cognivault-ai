from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_organization, get_db, require_roles
from app.models import AgentDecisionLog, LlmUsageRecord, Organization, RoleName, User
from app.services.agents import (
    AgentDecision,
    AgentType,
    bootstrap_agent_registry,
    dispatch,
    list_agents,
)


router = APIRouter(tags=["agents"])


class AgentInfoResponse(BaseModel):
    agent_type: str
    display_name: str
    description: str


class AgentDecisionResponse(BaseModel):
    agent_type: str
    intent: str
    confidence: float
    risk: str
    requires_human: bool
    action: str | None = None
    reason: str | None = None
    payload: dict = Field(default_factory=dict)
    tenant_id: int | None = None
    organization_id: int | None = None
    request_id: str | None = None
    created_at: str


class AgentDispatchRequest(BaseModel):
    agent_type: AgentType
    message: str | None = Field(default=None, max_length=4000)
    answers: dict | None = None
    required_fields: list[str] | None = None
    tenant_id: int | None = None
    organization_id: int | None = None
    request_id: str | None = Field(default=None, max_length=120)


def _decision_payload(decision: AgentDecision) -> AgentDecisionResponse:
    data = decision.to_dict()
    return AgentDecisionResponse(**data)


@router.get("/agents", response_model=list[AgentInfoResponse])
def get_agents(
    _: User = Depends(require_roles(RoleName.OPERATOR, RoleName.ADMIN)),
) -> list[AgentInfoResponse]:
    bootstrap_agent_registry()
    return [
        AgentInfoResponse(
            agent_type=agent.agent_type.value,
            display_name=agent.display_name,
            description=agent.description,
        )
        for agent in list_agents()
    ]


class AgentDecisionLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_type: str
    intent: str
    confidence: float
    risk: str
    requires_human: bool
    action: str | None = None
    reason: str | None = None
    organization_id: int | None = None
    clinic_id: int | None = None
    conversation_id: int | None = None
    chat_session_id: int | None = None
    user_id: int | None = None
    request_id: str | None = None
    payload_json: dict = Field(default_factory=dict)
    created_at: datetime


@router.get("/agents/decisions", response_model=list[AgentDecisionLogResponse])
def get_agent_decisions(
    agent_type: AgentType | None = Query(default=None),
    requires_human: bool | None = Query(default=None),
    risk: str | None = Query(default=None, pattern="^(low|medium|high)$"),
    conversation_id: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _: User = Depends(require_roles(RoleName.OPERATOR, RoleName.ADMIN)),
    organization: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> list[AgentDecisionLogResponse]:
    stmt = select(AgentDecisionLog).where(AgentDecisionLog.organization_id == organization.id)
    if agent_type is not None:
        stmt = stmt.where(AgentDecisionLog.agent_type == agent_type.value)
    if requires_human is not None:
        stmt = stmt.where(AgentDecisionLog.requires_human == requires_human)
    if risk is not None:
        stmt = stmt.where(AgentDecisionLog.risk == risk)
    if conversation_id is not None:
        stmt = stmt.where(AgentDecisionLog.conversation_id == conversation_id)
    stmt = stmt.order_by(AgentDecisionLog.created_at.desc()).limit(limit)
    return [AgentDecisionLogResponse.model_validate(row) for row in db.scalars(stmt)]


@router.get("/agents/decisions/{decision_id}", response_model=AgentDecisionLogResponse)
def get_agent_decision_detail(
    decision_id: int,
    _: User = Depends(require_roles(RoleName.OPERATOR, RoleName.ADMIN)),
    organization: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> AgentDecisionLogResponse:
    row = db.scalars(
        select(AgentDecisionLog).where(
            AgentDecisionLog.id == decision_id,
            AgentDecisionLog.organization_id == organization.id,
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Decision not found")
    return AgentDecisionLogResponse.model_validate(row)


@router.post("/agents/dispatch", response_model=AgentDecisionResponse)
def post_agent_dispatch(
    payload: AgentDispatchRequest,
    _: User = Depends(require_roles(RoleName.OPERATOR, RoleName.ADMIN)),
) -> AgentDecisionResponse:
    bootstrap_agent_registry()
    context = {
        "message": payload.message,
        "answers": payload.answers or {},
        "required_fields": payload.required_fields or [],
        "tenant_id": payload.tenant_id,
        "organization_id": payload.organization_id,
        "request_id": payload.request_id,
    }
    try:
        decision = dispatch(payload.agent_type, context)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _decision_payload(decision)


# ─── LLM Usage / Cost Summary ───────────────────────────────────────────────
class UsageSummaryByModel(BaseModel):
    model: str
    provider: str
    calls: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float


class UsageSummaryResponse(BaseModel):
    range_days: int
    total_calls: int
    total_tokens: int
    total_cost_usd: float
    by_model: list[UsageSummaryByModel]
    by_agent_type: dict[str, float]   # agent_type → cost_usd


@router.get("/agents/usage/summary", response_model=UsageSummaryResponse)
def get_usage_summary(
    days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleName.OPERATOR, RoleName.ADMIN)),
    organization: Organization | None = Depends(get_current_organization),
) -> UsageSummaryResponse:
    """LLM token + maliyet özeti — son N gün, organizasyon scope'lu."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    from sqlalchemy import or_
    base_filter = [LlmUsageRecord.created_at >= since]
    if organization is not None:
        # Legacy kayıtlar (organization_id IS NULL) admin'in default org'una dahil edilsin —
        # böylece Phase 1 öncesi veri ve customer/staff dağıtık org'lar görünür kalır.
        base_filter.append(
            or_(
                LlmUsageRecord.organization_id == organization.id,
                LlmUsageRecord.organization_id.is_(None),
            )
        )

    # Toplam metrikler
    totals = db.execute(
        select(
            func.count(LlmUsageRecord.id),
            func.coalesce(func.sum(LlmUsageRecord.total_tokens), 0),
            func.coalesce(func.sum(LlmUsageRecord.estimated_cost_usd), 0.0),
        ).where(*base_filter)
    ).one()
    total_calls, total_tokens, total_cost = totals

    # Model bazlı kırılım
    model_rows = db.execute(
        select(
            LlmUsageRecord.model,
            LlmUsageRecord.provider,
            func.count(LlmUsageRecord.id),
            func.coalesce(func.sum(LlmUsageRecord.prompt_tokens), 0),
            func.coalesce(func.sum(LlmUsageRecord.completion_tokens), 0),
            func.coalesce(func.sum(LlmUsageRecord.total_tokens), 0),
            func.coalesce(func.sum(LlmUsageRecord.estimated_cost_usd), 0.0),
        )
        .where(*base_filter)
        .group_by(LlmUsageRecord.model, LlmUsageRecord.provider)
        .order_by(func.sum(LlmUsageRecord.estimated_cost_usd).desc())
    ).all()
    by_model = [
        UsageSummaryByModel(
            model=row[0],
            provider=row[1],
            calls=int(row[2]),
            prompt_tokens=int(row[3]),
            completion_tokens=int(row[4]),
            total_tokens=int(row[5]),
            cost_usd=round(float(row[6]), 4),
        )
        for row in model_rows
    ]

    # Agent type kırılımı (None'lar "unknown" altında toplanır)
    agent_rows = db.execute(
        select(
            LlmUsageRecord.agent_type,
            func.coalesce(func.sum(LlmUsageRecord.estimated_cost_usd), 0.0),
        )
        .where(*base_filter)
        .group_by(LlmUsageRecord.agent_type)
    ).all()
    by_agent: dict[str, float] = {}
    for agent_type, cost in agent_rows:
        key = agent_type or "unknown"
        by_agent[key] = round(float(cost), 4)

    return UsageSummaryResponse(
        range_days=days,
        total_calls=int(total_calls),
        total_tokens=int(total_tokens),
        total_cost_usd=round(float(total_cost), 4),
        by_model=by_model,
        by_agent_type=by_agent,
    )
