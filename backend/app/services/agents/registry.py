"""Generic agent registry and decision contract.

The registry is process-local (an in-memory dict) and intentionally simple — it
exists today so feature work can target a stable interface without yet committing
to a persistent agent table or external orchestrator. Decision objects are
JSON-serialisable so they can be persisted to `metadata_json` columns or shipped
to a future `agent_decision_logs` table.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class AgentType(str, Enum):
    APPOINTMENT = "appointment"
    SUPPORT = "support"
    FORM = "form"
    ROUTING = "routing"
    CORPORATE_ASSISTANT = "corporate_assistant"


class DecisionRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class AgentDecision:
    """A structured record of one agent's choice for a single inbound request.

    Every field is optional except `agent_type` and `intent` so existing services
    can adopt the contract incrementally. `requires_human` plus `risk` capture the
    safety boundary; `action` and `payload` describe the concrete next step.
    """

    agent_type: AgentType
    intent: str
    confidence: float = 0.0
    risk: DecisionRisk = DecisionRisk.LOW
    requires_human: bool = False
    reason: str | None = None
    action: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    tenant_id: int | None = None
    organization_id: int | None = None
    request_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["agent_type"] = self.agent_type.value
        data["risk"] = self.risk.value
        data["created_at"] = self.created_at.isoformat()
        return data


class BaseAgent:
    """Adapter base class — concrete agents implement `decide`."""

    agent_type: AgentType
    display_name: str = ""
    description: str = ""

    def decide(self, context: dict[str, Any]) -> AgentDecision:  # pragma: no cover - interface
        raise NotImplementedError


_REGISTRY: dict[AgentType, BaseAgent] = {}


def register_agent(agent: BaseAgent) -> None:
    if agent.agent_type in _REGISTRY:
        logger.debug("Overriding registered agent for %s", agent.agent_type.value)
    _REGISTRY[agent.agent_type] = agent


def get_agent(agent_type: AgentType) -> BaseAgent | None:
    return _REGISTRY.get(agent_type)


def list_agents() -> list[BaseAgent]:
    return list(_REGISTRY.values())


def dispatch(
    agent_type: AgentType,
    context: dict[str, Any],
    *,
    log_fn: Callable[[AgentDecision], None] | None = None,
) -> AgentDecision:
    agent = _REGISTRY.get(agent_type)
    if agent is None:
        decision = AgentDecision(
            agent_type=agent_type,
            intent="unknown",
            confidence=0.0,
            risk=DecisionRisk.HIGH,
            requires_human=True,
            reason=f"No agent registered for {agent_type.value}",
        )
    else:
        decision = agent.decide(context)
    if log_fn is not None:
        log_fn(decision)
    return decision


# --- Built-in mock agents ----------------------------------------------------
#
# These exist so an out-of-the-box install has working demo flows even without
# OpenAI / Anthropic credentials. Real implementations layered on top of the
# existing services will replace them in later phases.


class _MockAppointmentAgent(BaseAgent):
    agent_type = AgentType.APPOINTMENT
    display_name = "Appointment Agent (demo)"
    description = "Routes booking-style intents toward the appointment service."

    def decide(self, context: dict[str, Any]) -> AgentDecision:
        message = (context.get("message") or "").lower()
        wants_booking = any(token in message for token in ("randevu", "appointment", "booking"))
        return AgentDecision(
            agent_type=self.agent_type,
            intent="appointment_request" if wants_booking else "general",
            confidence=0.85 if wants_booking else 0.4,
            risk=DecisionRisk.LOW,
            requires_human=not wants_booking,
            action="create_appointment_draft" if wants_booking else "ask_clarification",
            reason="keyword_match" if wants_booking else "no_explicit_booking_keyword",
            tenant_id=context.get("tenant_id"),
            organization_id=context.get("organization_id"),
            request_id=context.get("request_id"),
        )


class _MockRoutingAgent(BaseAgent):
    agent_type = AgentType.ROUTING
    display_name = "Routing Agent (demo)"
    description = "Decides whether a message stays with the bot, escalates to human, or routes to a department."

    def decide(self, context: dict[str, Any]) -> AgentDecision:
        message = (context.get("message") or "").lower()
        emergency_tokens = ("acil", "kanama", "bayild", "nefes alam", "gogus agri")
        if any(token in message for token in emergency_tokens):
            return AgentDecision(
                agent_type=self.agent_type,
                intent="emergency_escalation",
                confidence=0.99,
                risk=DecisionRisk.HIGH,
                requires_human=True,
                action="notify_doctor_inbox",
                reason="emergency_keyword",
                tenant_id=context.get("tenant_id"),
                organization_id=context.get("organization_id"),
                request_id=context.get("request_id"),
            )
        return AgentDecision(
            agent_type=self.agent_type,
            intent="auto_reply_safe",
            confidence=0.7,
            risk=DecisionRisk.LOW,
            requires_human=False,
            action="continue_bot_flow",
            tenant_id=context.get("tenant_id"),
            organization_id=context.get("organization_id"),
            request_id=context.get("request_id"),
        )


class _MockSupportAgent(BaseAgent):
    agent_type = AgentType.SUPPORT
    display_name = "Support Agent (demo)"
    description = "Generic FAQ / support intent classifier."

    def decide(self, context: dict[str, Any]) -> AgentDecision:
        return AgentDecision(
            agent_type=self.agent_type,
            intent="support_query",
            confidence=0.6,
            risk=DecisionRisk.LOW,
            requires_human=False,
            action="reply_with_knowledge_base",
            tenant_id=context.get("tenant_id"),
            organization_id=context.get("organization_id"),
            request_id=context.get("request_id"),
        )


class _MockFormAgent(BaseAgent):
    agent_type = AgentType.FORM
    display_name = "Form Agent (demo)"
    description = "Collects structured intake/application answers (e.g. pre-intake forms)."

    def decide(self, context: dict[str, Any]) -> AgentDecision:
        answers = context.get("answers") or {}
        remaining = context.get("required_fields") or []
        missing = [field for field in remaining if field not in answers]
        is_complete = not missing
        return AgentDecision(
            agent_type=self.agent_type,
            intent="form_progress",
            confidence=1.0 if is_complete else 0.5,
            risk=DecisionRisk.LOW,
            requires_human=False,
            action="persist_pre_intake" if is_complete else "ask_next_question",
            payload={"missing_fields": missing},
            tenant_id=context.get("tenant_id"),
            organization_id=context.get("organization_id"),
            request_id=context.get("request_id"),
        )


class _MockCorporateAssistantAgent(BaseAgent):
    agent_type = AgentType.CORPORATE_ASSISTANT
    display_name = "Corporate Assistant (demo)"
    description = "Internal employee assistant for operator/admin workflows."

    def decide(self, context: dict[str, Any]) -> AgentDecision:
        return AgentDecision(
            agent_type=self.agent_type,
            intent="corporate_internal_query",
            confidence=0.65,
            risk=DecisionRisk.MEDIUM,
            requires_human=False,
            action="summarize_for_operator",
            tenant_id=context.get("tenant_id"),
            organization_id=context.get("organization_id"),
            request_id=context.get("request_id"),
        )


def bootstrap_agent_registry() -> None:
    """Idempotently registers the built-in mock agents at startup.

    Real implementations can call `register_agent` later to override these defaults
    without changing the dispatch contract.
    """

    for agent in (
        _MockAppointmentAgent(),
        _MockRoutingAgent(),
        _MockSupportAgent(),
        _MockFormAgent(),
        _MockCorporateAssistantAgent(),
    ):
        if agent.agent_type not in _REGISTRY:
            register_agent(agent)
