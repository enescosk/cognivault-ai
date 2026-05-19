"""Agent registry — generic abstraction over Cognivault's AI agent types.

This module deliberately does **not** replace the existing clinical / chat / intelligence
services. It exposes a tenant-aware registry so that future enterprise features can
dispatch work to a typed agent (`appointment`, `support`, `form`, `routing`,
`corporate_assistant`) and so that decisions can be logged uniformly.

Existing services keep their public APIs; they are registered as adapters here so a
single observability/audit pipeline can grow around them in later phases.
"""

from app.services.agents.logging import build_decision, record_agent_decision
from app.services.agents.registry import (
    AgentDecision,
    AgentType,
    BaseAgent,
    DecisionRisk,
    bootstrap_agent_registry,
    dispatch,
    get_agent,
    list_agents,
    register_agent,
)

__all__ = [
    "AgentDecision",
    "AgentType",
    "BaseAgent",
    "DecisionRisk",
    "bootstrap_agent_registry",
    "build_decision",
    "dispatch",
    "get_agent",
    "list_agents",
    "record_agent_decision",
    "register_agent",
]
