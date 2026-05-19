from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.dependencies import require_roles
from app.models import RoleName, User
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
