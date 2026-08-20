"""Deterministic integer pricing used by the local Run budget."""

from bearagent.domain.agent import ModelPricing

_TOKENS_PER_MILLION = 1_000_000


def estimate_model_cost_microusd(
    input_tokens: int,
    output_tokens: int,
    pricing: ModelPricing,
) -> int:
    """Round input and output estimates separately to whole micro-USD."""
    if input_tokens < 0 or output_tokens < 0:
        raise ValueError("token usage cannot be negative")
    return _rounded_component(
        input_tokens,
        pricing.input_microusd_per_million_tokens,
    ) + _rounded_component(
        output_tokens,
        pricing.output_microusd_per_million_tokens,
    )


def _rounded_component(tokens: int, rate: int) -> int:
    numerator = tokens * rate
    return (numerator + _TOKENS_PER_MILLION - 1) // _TOKENS_PER_MILLION
