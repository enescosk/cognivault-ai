"""Multi-Agent Architecture for CogniVault AI.

Instead of one monolithic orchestrator, intent is classified first by a
cheap router agent, then a specialized sub-agent handles the task.

Tiers:
  RouterAgent   — Haiku / cheap model — classifies intent in <200ms
  AppointmentAgent  — Sonnet / full model — handles booking workflow with tools
  EscalationAgent   — Sonnet — packages context for human handoff
  SmallTalkAgent    — zero-cost — handles greetings/thanks with canned replies

Adding a new agent type: create a new *Agent class with a `can_handle` and
`run` method, then register it in AgentRouter.route().
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Literal

from app.ai.runtime import complete_json, select_llm_runtime
from app.core.config import get_settings

logger = logging.getLogger(__name__)

IntentType = Literal[
    "appointment_booking",
    "outreach_request",
    "smalltalk",
    "escalation_request",
    "application_submission",
    "unknown",
]


@dataclass
class RoutedIntent:
    intent: IntentType
    confidence: float
    language: str
    sentiment: str
    escalate: bool = False
    router_used: str = "rule_based"
    raw: dict = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# INTENT ROUTER AGENT
# Uses the cheapest available model to classify intent before routing.
# Falls back to rule-based when no LLM is configured.
# ─────────────────────────────────────────────────────────────────────────────

_ROUTER_SYSTEM = """You are an intent classification engine. Respond ONLY with valid JSON.

Classify the user message into one of these intents:
- appointment_booking: user wants to book, schedule, or manage an appointment
- outreach_request: user wants to contact an external company or find contact info
- smalltalk: greeting, thanks, farewell, casual chat — no task required
- escalation_request: user explicitly wants to speak to a human / manager
- application_submission: user wants to submit a form or application
- unknown: none of the above

Also detect:
- language: "tr" or "en"
- sentiment: "frustrated" | "urgent" | "confused" | "happy" | "neutral"
- confidence: 0.0–1.0

Respond exactly:
{"intent":"<intent>","confidence":<0.0-1.0>,"language":"<tr|en>","sentiment":"<sentiment>"}"""


def route_intent(user_message: str, history_summary: str = "") -> RoutedIntent:
    """
    Classify intent using cheapest available model.
    Returns RoutedIntent with intent, confidence, language, sentiment.
    """
    settings = get_settings()
    runtime = select_llm_runtime()

    # Try LLM classification first (uses Haiku-equivalent cheap model)
    if runtime is not None:
        user_prompt = f"Message: {user_message}"
        if history_summary:
            user_prompt = f"Context: {history_summary}\n\nMessage: {user_message}"

        result = complete_json(
            system_prompt=_ROUTER_SYSTEM,
            user_prompt=user_prompt,
            max_tokens=100,
            temperature=0.1,
        )
        if result and "intent" in result:
            return RoutedIntent(
                intent=result.get("intent", "unknown"),
                confidence=float(result.get("confidence", 0.7)),
                language=result.get("language", "en"),
                sentiment=result.get("sentiment", "neutral"),
                router_used="llm",
                raw=result,
            )

    # Rule-based fallback
    return _rule_based_route(user_message)


def _rule_based_route(text: str) -> RoutedIntent:
    lower = text.lower()

    # Language detection
    tr_markers = ["ş", "ğ", "ı", "ç", "ö", "ü", "merhaba", "randevu", "teşekkür"]
    language = "tr" if any(m in text for m in tr_markers) else "en"

    # Sentiment
    if any(w in lower for w in ["saçmalık", "rezalet", "frustrated", "ridiculous", "unacceptable"]):
        sentiment = "frustrated"
    elif any(w in lower for w in ["acil", "urgent", "asap", "hemen"]):
        sentiment = "urgent"
    elif any(w in lower for w in ["teşekkür", "thank", "great", "harika"]):
        sentiment = "happy"
    else:
        sentiment = "neutral"

    # Intent
    if any(w in lower for w in ["insan", "operatör", "yetkiliy", "human", "agent", "manager", "speak to"]):
        return RoutedIntent(intent="escalation_request", confidence=0.9, language=language, sentiment=sentiment)
    if any(w in lower for w in ["randevu", "appointment", "book", "schedule", "rezervasyon"]):
        return RoutedIntent(intent="appointment_booking", confidence=0.85, language=language, sentiment=sentiment)
    if any(w in lower for w in ["merhaba", "hello", "hi ", "selam", "teşekkür", "thanks", "bye", "görüşürüz"]):
        return RoutedIntent(intent="smalltalk", confidence=0.9, language=language, sentiment=sentiment)
    if any(w in lower for w in ["ara", "iletişim", "contact", "call", "telefon", "görüşme"]):
        return RoutedIntent(intent="outreach_request", confidence=0.75, language=language, sentiment=sentiment)

    return RoutedIntent(intent="unknown", confidence=0.4, language=language, sentiment=sentiment)


# ─────────────────────────────────────────────────────────────────────────────
# ESCALATION AGENT
# Packages conversation context for human handoff.
# ─────────────────────────────────────────────────────────────────────────────

_ESCALATION_SYSTEM = """You are an escalation package builder. When a customer needs a human agent,
create a concise handoff summary in JSON with:
- reason: why they need human help (1 sentence)
- urgency: "low" | "medium" | "high"
- key_facts: list of up to 3 things the human agent needs to know
- suggested_department: which team should handle this

Respond only with JSON."""


@dataclass
class EscalationPackage:
    reason: str
    urgency: str
    key_facts: list[str]
    suggested_department: str
    raw_summary: str = ""


def build_escalation_package(
    user_message: str,
    conversation_summary: str,
    language: str,
) -> EscalationPackage:
    """Build a structured handoff package for human escalation."""
    runtime = select_llm_runtime()
    if runtime is None:
        return EscalationPackage(
            reason=user_message[:200],
            urgency="medium",
            key_facts=[f"User requested escalation: {user_message[:100]}"],
            suggested_department="Technical Support",
        )

    user_prompt = (
        f"Language: {language}\n"
        f"Conversation so far: {conversation_summary[:500]}\n"
        f"Latest message: {user_message}"
    )
    result = complete_json(
        system_prompt=_ESCALATION_SYSTEM,
        user_prompt=user_prompt,
        max_tokens=300,
        temperature=0.3,
    )
    if result:
        return EscalationPackage(
            reason=result.get("reason", "Customer requested human assistance"),
            urgency=result.get("urgency", "medium"),
            key_facts=result.get("key_facts", []),
            suggested_department=result.get("suggested_department", "Support"),
            raw_summary=json.dumps(result),
        )
    return EscalationPackage(
        reason=user_message[:200],
        urgency="medium",
        key_facts=[],
        suggested_department="Support",
    )


# ─────────────────────────────────────────────────────────────────────────────
# SENTIMENT ESCALATION TRACKER
# Tracks frustrated turns; escalates after threshold is crossed.
# ─────────────────────────────────────────────────────────────────────────────

FRUSTRATION_ESCALATION_THRESHOLD = 2


def should_auto_escalate(workflow_state: dict, current_sentiment: str) -> bool:
    """Returns True when the user has been frustrated for too many consecutive turns."""
    if current_sentiment != "frustrated":
        return False
    count = workflow_state.get("consecutive_frustrated_turns", 0)
    return count >= FRUSTRATION_ESCALATION_THRESHOLD


def update_frustration_counter(workflow_state: dict, sentiment: str) -> dict:
    """Update the consecutive frustrated turns counter in workflow state."""
    state = dict(workflow_state)
    if sentiment == "frustrated":
        state["consecutive_frustrated_turns"] = state.get("consecutive_frustrated_turns", 0) + 1
    else:
        state["consecutive_frustrated_turns"] = 0
    return state


def escalation_offer_message(language: str) -> str:
    if language == "tr":
        return (
            "Durumu anlıyorum ve bu kadar sorun yaşıyor olmandan üzüntü duyuyorum. "
            "Seni daha hızlı yardım edebilecek bir uzman ekibine bağlayabilirim. "
            "İster misiniz? (Evet / Hayır)"
        )
    return (
        "I understand your frustration and I'm sorry you're having such a difficult experience. "
        "I can connect you with a specialist who can help you faster. "
        "Would you like that? (Yes / No)"
    )
