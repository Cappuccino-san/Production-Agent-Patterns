"""Unit tests for models, schemas, and pricing calculations."""

import pytest
from pydantic import ValidationError
from app.models import AgentTaskRunRequest, AgentTaskRunResponse, CostLedgerEntry, CostStatus
from app.pricing import calculate_step_cost, evaluate_cost_kill_switch


def test_pricing_calculation_gpt4o():
    # 1,000 prompt tokens ($0.005) + 1,000 completion tokens ($0.015) = $0.020
    cost = calculate_step_cost("gpt-4o", 1000, 1000)
    assert cost == 0.02


def test_pricing_calculation_gpt4o_mini():
    # 1,000 prompt tokens ($0.00015) + 1,000 completion tokens ($0.0006) = $0.00075
    cost = calculate_step_cost("gpt-4o-mini", 1000, 1000)
    assert cost == 0.00075


def test_evaluate_cost_kill_switch_within_budget():
    triggered, fallback, reason = evaluate_cost_kill_switch(
        current_spend_usd=0.10,
        projected_step_cost_usd=0.05,
        current_depth=2,
        max_spend_usd=0.50,
        max_depth=5,
    )
    assert triggered is False
    assert fallback is False


def test_evaluate_cost_kill_switch_breach():
    triggered, fallback, reason = evaluate_cost_kill_switch(
        current_spend_usd=0.45,
        projected_step_cost_usd=0.08,  # total 0.53 >= 0.50
        current_depth=3,
        max_spend_usd=0.50,
        max_depth=5,
    )
    assert triggered is True
    assert fallback is True
    assert "Spend limit reached" in reason


def test_evaluate_cost_kill_switch_depth_breach():
    triggered, fallback, reason = evaluate_cost_kill_switch(
        current_spend_usd=0.10,
        projected_step_cost_usd=0.01,
        current_depth=6,  # depth > max_depth
        max_spend_usd=0.50,
        max_depth=5,
    )
    assert triggered is True
    assert "Maximum loop depth exceeded" in reason


def test_agent_task_request_validation():
    with pytest.raises(ValidationError):
        AgentTaskRunRequest(prompt="ab")  # min_length 3

    valid = AgentTaskRunRequest(prompt="Valid task prompt", max_iterations=3)
    assert valid.prompt == "Valid task prompt"
    assert valid.max_iterations == 3
