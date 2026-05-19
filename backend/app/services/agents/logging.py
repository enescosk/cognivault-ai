"""Persistence layer for AgentDecision objects.

`record_agent_decision` is the single seam between the in-memory decision
contract (`app.services.agents.registry.AgentDecision`) and the on-disk
`agent_decision_logs` table. Callers across clinical, chat, and intelligence
services pass the same shape so the operator UI can query every decision the
system has made in one place.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models import AgentDecisionLog
from app.services.agents.registry import AgentDecision, AgentType, DecisionRisk

logger = logging.getLogger(__name__)


def record_agent_decision(
    db: Session,
    decision: AgentDecision,
    *,
    clinic_id: int | None = None,
    conversation_id: int | None = None,
    chat_session_id: int | None = None,
    user_id: int | None = None,
    extra_payload: dict[str, Any] | None = None,
) -> AgentDecisionLog:
    payload: dict[str, Any] = dict(decision.payload or {})
    if extra_payload:
        payload.update(extra_payload)

    row = AgentDecisionLog(
        agent_type=decision.agent_type.value,
        intent=decision.intent,
        confidence=float(decision.confidence or 0.0),
        risk=decision.risk.value,
        requires_human=bool(decision.requires_human),
        action=decision.action,
        reason=decision.reason,
        organization_id=decision.organization_id,
        clinic_id=clinic_id if clinic_id is not None else decision.tenant_id,
        conversation_id=conversation_id,
        chat_session_id=chat_session_id,
        user_id=user_id,
        request_id=decision.request_id,
        payload_json=payload,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def build_decision(
    *,
    agent_type: AgentType,
    intent: str,
    confidence: float = 0.0,
    risk: DecisionRisk = DecisionRisk.LOW,
    requires_human: bool = False,
    action: str | None = None,
    reason: str | None = None,
    payload: dict[str, Any] | None = None,
    organization_id: int | None = None,
    request_id: str | None = None,
) -> AgentDecision:
    """Convenience constructor — callers don't have to import the dataclass."""

    return AgentDecision(
        agent_type=agent_type,
        intent=intent,
        confidence=confidence,
        risk=risk,
        requires_human=requires_human,
        action=action,
        reason=reason,
        payload=payload or {},
        organization_id=organization_id,
        request_id=request_id,
    )
