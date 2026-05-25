"""Static pricing table for LLM cost estimation.

Prices are USD per 1M tokens (input / output) as published by providers.
Update this file whenever a new model is wired up or rates change — historical
`LlmUsageRecord` rows store the cost as it was when written, so old data is
unaffected by edits here.
"""

from __future__ import annotations

# (input_per_1m_usd, output_per_1m_usd)
PRICING: dict[str, tuple[float, float]] = {
    # OpenAI
    "gpt-4.1-mini":         (0.40, 1.60),
    "gpt-4o-mini":          (0.15, 0.60),
    "gpt-4o":               (2.50, 10.00),
    "gpt-4-turbo":          (10.00, 30.00),
    # Anthropic
    "claude-sonnet-4-5":    (3.00, 15.00),
    "claude-3-5-sonnet":    (3.00, 15.00),
    "claude-3-5-haiku":     (0.80, 4.00),
    "claude-3-5-haiku-latest": (0.80, 4.00),
    "claude-3-opus":        (15.00, 75.00),
    "claude-3-haiku":       (0.25, 1.25),
}

# Yeni / bilinmeyen modeller için ortalama fiyat — log'da görünmesi şart, $0 olarak göstermek yanıltıcı
FALLBACK_PRICING = (1.00, 3.00)


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    rate_in, rate_out = PRICING.get(model.lower(), FALLBACK_PRICING)
    cost = (prompt_tokens * rate_in + completion_tokens * rate_out) / 1_000_000
    return round(cost, 6)


def provider_for(model: str) -> str:
    name = model.lower()
    if name.startswith("claude"):
        return "anthropic"
    if name.startswith("gpt") or name.startswith("o1") or name.startswith("o3"):
        return "openai"
    return "unknown"
