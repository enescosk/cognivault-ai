from __future__ import annotations

from dataclasses import dataclass
import json

from openai import OpenAI

from app.core.config import get_settings


@dataclass(frozen=True)
class LLMRuntime:
    provider: str
    model: str
    client: OpenAI
    is_local: bool


def local_llm_enabled() -> bool:
    settings = get_settings()
    return bool(settings.local_llm_base_url.strip())


def openai_llm_enabled() -> bool:
    settings = get_settings()
    return bool(settings.openai_api_key.strip())


def select_llm_runtime() -> LLMRuntime | None:
    settings = get_settings()
    preferred = settings.preferred_llm_provider.strip().lower()

    if preferred in {"local", "auto"} and local_llm_enabled():
        return LLMRuntime(
            provider="local_openai_compatible",
            model=settings.local_llm_model,
            client=OpenAI(
                api_key=settings.local_llm_api_key or "local",
                base_url=settings.local_llm_base_url.rstrip("/"),
            ),
            is_local=True,
        )

    if preferred in {"openai", "auto"} and openai_llm_enabled():
        return LLMRuntime(
            provider="openai",
            model=settings.openai_model,
            client=OpenAI(api_key=settings.openai_api_key),
            is_local=False,
        )

    return None


def llm_capabilities() -> dict:
    settings = get_settings()
    runtime = select_llm_runtime()
    return {
        "active_provider": runtime.provider if runtime else "local_rules",
        "active_model": runtime.model if runtime else "cognivault-rule-engine",
        "preferred_provider": settings.preferred_llm_provider,
        "local_llm_configured": local_llm_enabled(),
        "openai_configured": openai_llm_enabled(),
        "offline_capable": True,
        "tool_calling": bool(runtime),
        "fallback_engine": "local_guided_workflow",
    }


def complete_json(
    *,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 700,
    temperature: float = 0.2,
) -> dict | None:
    """
    Provider-neutral JSON completion through the selected OpenAI-compatible runtime.

    This is the single gateway for local-first model calls that need structured
    output. Callers can fall back to deterministic rules when no runtime exists.
    """
    runtime = select_llm_runtime()
    if runtime is None:
        return None

    response = runtime.client.chat.completions.create(
        model=runtime.model,
        temperature=temperature,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content or ""
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(content[start : end + 1])
            except json.JSONDecodeError:
                return None
    return None
