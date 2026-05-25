"""Single seam for writing LLM telemetry to the database.

Every call site that invokes OpenAI or Anthropic should pass the resulting
usage object (or token counts) through `record_llm_usage` so the admin
dashboard's cost panel and per-tenant budgets have a consistent feed.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models import LlmUsageRecord
from app.services.llm_pricing import estimate_cost_usd, provider_for

logger = logging.getLogger(__name__)


def record_llm_usage(
    db: Session,
    *,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    agent_type: str | None = None,
    organization_id: int | None = None,
    user_id: int | None = None,
    request_id: str | None = None,
) -> LlmUsageRecord | None:
    """Persist a single LLM call's token usage + estimated cost.

    Returns None on failure — telemetry must never break the request path.
    """
    try:
        total = (prompt_tokens or 0) + (completion_tokens or 0)
        if total == 0:
            return None
        cost = estimate_cost_usd(model, prompt_tokens, completion_tokens)
        row = LlmUsageRecord(
            provider=provider_for(model),
            model=model,
            agent_type=agent_type,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total,
            estimated_cost_usd=cost,
            organization_id=organization_id,
            user_id=user_id,
            request_id=request_id,
        )
        db.add(row)
        db.commit()
        return row
    except Exception as exc:  # noqa: BLE001
        logger.warning("llm_usage record failed: %s", exc)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None


def extract_openai_usage(response: Any) -> tuple[int, int]:
    """OpenAI response → (prompt_tokens, completion_tokens). Tolerates missing usage."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return (0, 0)
    return (int(getattr(usage, "prompt_tokens", 0) or 0),
            int(getattr(usage, "completion_tokens", 0) or 0))


def extract_anthropic_usage(response: Any) -> tuple[int, int]:
    """Anthropic response → (input_tokens, output_tokens)."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return (0, 0)
    return (int(getattr(usage, "input_tokens", 0) or 0),
            int(getattr(usage, "output_tokens", 0) or 0))
