"""Pricing calculations and cost kill-switch threshold rules."""

from typing import Tuple

MODEL_PRICING_PER_1K = {
    "gpt-4o": {
        "prompt": 0.005,      # $5.00 / 1M tokens
        "completion": 0.015,  # $15.00 / 1M tokens
    },
    "gpt-4o-mini": {
        "prompt": 0.00015,    # $0.15 / 1M tokens
        "completion": 0.0006, # $0.60 / 1M tokens
    },
}


def calculate_step_cost(model_name: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Calculate exact USD cost for a token hop."""
    pricing = MODEL_PRICING_PER_1K.get(model_name, MODEL_PRICING_PER_1K["gpt-4o-mini"])
    cost = (prompt_tokens / 1000.0) * pricing["prompt"] + (completion_tokens / 1000.0) * pricing["completion"]
    return round(cost, 6)


def evaluate_cost_kill_switch(
    current_spend_usd: float,
    projected_step_cost_usd: float,
    current_depth: int,
    max_spend_usd: float = 0.50,
    max_depth: int = 5,
) -> Tuple[bool, bool, str]:
    """
    Evaluates loop depth and projected spend against threshold ($0.50).
    Returns (kill_switch_triggered, should_fallback, reason).
    """
    projected_total = current_spend_usd + projected_step_cost_usd

    if projected_total >= max_spend_usd:
        return True, True, f"Spend limit reached: ${projected_total:.4f} >= ${max_spend_usd:.2f} threshold"

    if current_depth > max_depth:
        return True, True, f"Maximum loop depth exceeded: {current_depth} > {max_depth}"

    return False, False, "Operating within normal cost budget"
