"""Anthropic runtime — Claude with prompt caching.

Prompt caching saves ~90% of input tokens on the static system block.
The system prompt is marked with cache_control=ephemeral; Anthropic caches
it for 5 minutes. On cache hit, only the new user message is billed.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Generator
from dataclasses import dataclass

import anthropic

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AnthropicRuntime:
    model: str
    intent_model: str
    client: anthropic.Anthropic


def anthropic_enabled() -> bool:
    return bool(get_settings().anthropic_api_key.strip())


def get_anthropic_runtime() -> AnthropicRuntime | None:
    settings = get_settings()
    if not settings.anthropic_api_key.strip():
        return None
    return AnthropicRuntime(
        model=settings.anthropic_model,
        intent_model=settings.anthropic_intent_model,
        client=anthropic.Anthropic(api_key=settings.anthropic_api_key),
    )


def build_cached_system(system_prompt: str, context_block: str) -> list[dict]:
    """
    Returns Anthropic system blocks with cache_control on the static prompt.

    The long system prompt is marked as ephemeral — Anthropic caches it for
    5 minutes so repeated calls only bill the dynamic context_block portion.
    """
    return [
        {
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": context_block,
        },
    ]


def convert_history_to_anthropic(messages: list[dict]) -> list[dict]:
    """Convert OpenAI-style message list to Anthropic format, merging consecutive same-role messages."""
    result: list[dict] = []
    for msg in messages:
        role = msg.get("role")
        if role == "system":
            continue
        if role in {"user", "assistant"}:
            content = msg.get("content") or ""
            if result and result[-1]["role"] == role:
                existing = result[-1]["content"]
                if isinstance(existing, str):
                    result[-1]["content"] = existing + "\n\n" + content
                else:
                    result[-1]["content"].append({"type": "text", "text": content})
            else:
                result.append({"role": role, "content": content})
    # Anthropic requires messages to start with user
    if result and result[0]["role"] == "assistant":
        result = result[1:]
    return result


def run_anthropic_agent(
    *,
    runtime: AnthropicRuntime,
    system_blocks: list[dict],
    messages: list[dict],
    tools: list[dict],
    max_iterations: int = 6,
    temperature: float = 0.65,
) -> tuple[str, list[dict]]:
    """
    Non-streaming Anthropic agent tool loop.

    Returns (final_text, updated_messages).
    Caller is responsible for extracting tool calls and updating messages.
    """
    history = list(messages)

    for _ in range(max_iterations):
        response = runtime.client.messages.create(
            model=runtime.model,
            max_tokens=2048,
            system=system_blocks,
            messages=history,
            tools=tools,
            temperature=temperature,
        )

        tool_uses = [b for b in response.content if b.type == "tool_use"]
        text_blocks = [b for b in response.content if b.type == "text"]
        text_content = " ".join(b.text for b in text_blocks)

        if not tool_uses or response.stop_reason != "tool_use":
            return text_content, history

        # Add assistant turn with tool_use blocks
        history.append({
            "role": "assistant",
            "content": [
                {"type": b.type, "id": b.id, "name": b.name, "input": b.input}
                if b.type == "tool_use"
                else {"type": "text", "text": b.text}
                for b in response.content
            ],
        })

        # Caller must handle tool execution and append tool_result messages
        # We return here so the orchestrator can execute tools and continue
        return "", history  # signal: tool_uses pending

    return "", history


def stream_anthropic_agent(
    *,
    runtime: AnthropicRuntime,
    system_blocks: list[dict],
    messages: list[dict],
    tools: list[dict],
    execute_tool_fn,
    max_iterations: int = 6,
    temperature: float = 0.65,
) -> Generator[str, None, None]:
    """
    Full streaming Anthropic agent with tool loop.

    Phase 1: tool loop (non-streaming, runs tools)
    Phase 2: streaming final response (no more tool calls)

    Yields SSE-formatted strings identical to stream_openai_agent.
    """
    def _sse(payload: dict) -> str:
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    history = list(messages)
    confirmation_card = None

    # Phase 1: tool loop
    for _ in range(max_iterations):
        response = runtime.client.messages.create(
            model=runtime.model,
            max_tokens=2048,
            system=system_blocks,
            messages=history,
            tools=tools,
            temperature=temperature,
        )

        tool_uses = [b for b in response.content if b.type == "tool_use"]

        if not tool_uses or response.stop_reason != "tool_use":
            # No more tools — break to streaming phase
            break

        # Signal tool starts to the frontend
        for tu in tool_uses:
            yield _sse({"t": "tool_start", "name": tu.name})

        # Build assistant turn
        history.append({
            "role": "assistant",
            "content": [
                {"type": b.type, "id": b.id, "name": b.name, "input": b.input}
                if b.type == "tool_use"
                else {"type": "text", "text": b.text}
                for b in response.content
            ],
        })

        # Execute each tool and collect results
        tool_results = []
        for tu in tool_uses:
            result, card = execute_tool_fn(name=tu.name, arguments=json.dumps(tu.input))
            if card:
                confirmation_card = card
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": json.dumps(result, default=str),
            })

        history.append({"role": "user", "content": tool_results})

    # Phase 2: streaming final response
    full_text = ""
    try:
        with runtime.client.messages.stream(
            model=runtime.model,
            max_tokens=2048,
            system=system_blocks,
            messages=history,
            tools=tools,
            temperature=temperature,
        ) as stream:
            for text in stream.text_stream:
                full_text += text
                yield _sse({"t": "tk", "v": text})
    except Exception as exc:
        logger.exception("anthropic_stream_failed")
        yield _sse({"t": "err", "code": "stream_failed", "v": str(exc)})
        return

    card_meta = confirmation_card.model_dump(mode="json") if confirmation_card else {}
    yield _sse({"t": "done", "card": card_meta or None, "_full_text": full_text})


def tool_specs_anthropic() -> list[dict]:
    """Anthropic tool format (input_schema instead of parameters, no 'type':'function' wrapper)."""
    return [
        {
            "name": "fetch_user_profile",
            "description": "Fetch the current authenticated user's profile and role information.",
            "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "validate_user_role",
            "description": "Validate whether the authenticated user can perform an action.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "required_role": {"type": "string"},
                    "action": {"type": "string"},
                    "target_user_id": {"type": "integer"},
                },
                "required": ["required_role", "action", "target_user_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "check_available_slots",
            "description": "List the next available appointment slots for a department.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "department": {"type": "string"},
                    "preferred_date": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["department"],
                "additionalProperties": False,
            },
        },
        {
            "name": "create_appointment",
            "description": "Create an appointment using a selected slot and collected customer information.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "slot_id": {"type": "integer"},
                    "purpose": {"type": "string"},
                    "contact_phone": {"type": "string"},
                    "notes": {"type": "string"},
                    "language": {"type": "string"},
                    "target_user_id": {"type": "integer"},
                },
                "required": ["slot_id", "purpose", "contact_phone", "language"],
                "additionalProperties": False,
            },
        },
        {
            "name": "save_user_phone",
            "description": "Save or update the user's phone number in their profile.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "phone": {"type": "string", "description": "Phone number to save, e.g. '+905301234567'"},
                },
                "required": ["phone"],
                "additionalProperties": False,
            },
        },
    ]
