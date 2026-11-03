"""Tests for LangGraph cost kill-switch graph and fallback routing."""

import pytest
from app.agent.graph import build_cost_guard_graph
from app.agent.state import CostAgentState
from app.models import CostStatus


def test_graph_normal_execution_under_budget():
    graph = build_cost_guard_graph()
    initial_state = CostAgentState(
        request_id="test-normal-run-001",
        prompt="Analyze revenue growth trends for Q3",
        force_spend_spike=False,
        max_iterations=2,
    )

    result = graph.invoke(initial_state)

    assert result["kill_switch_triggered"] is False
    assert result["fallback_engaged"] is False
    assert result["status"] == CostStatus.COMPLETED
    assert result["current_model"] == "gpt-4o"
    assert result["current_spend_usd"] < 0.50
    assert len(result["ledger"]) == 2


def test_graph_spend_spike_triggers_kill_switch_and_fallback():
    graph = build_cost_guard_graph()
    initial_state = CostAgentState(
        request_id="test-spike-run-002",
        prompt="Execute runaway token loop with recursive summarization",
        force_spend_spike=True,
        max_iterations=5,
    )

    result = graph.invoke(initial_state)

    assert result["kill_switch_triggered"] is True
    assert result["fallback_engaged"] is True
    assert result["current_model"] == "gpt-4o-mini"
    assert len(result["ledger"]) >= 2
    # The first step was gpt-4o with kill switch tripped, subsequent was gpt-4o-mini
    assert result["ledger"][0].model_used == "gpt-4o"
    assert result["ledger"][0].kill_switch_active is True
    assert result["ledger"][1].model_used == "gpt-4o-mini"


def test_graph_hard_halt_when_spend_exceeds_extreme_ceiling():
    graph = build_cost_guard_graph()
    # If state already starts above absolute ceiling ($0.60)
    initial_state = CostAgentState(
        request_id="test-halt-run-003",
        prompt="Pre-exhausted budget scenario",
        current_spend_usd=0.65,
        kill_switch_triggered=True,
        max_iterations=3,
    )

    result = graph.invoke(initial_state)

    assert result["status"] == CostStatus.HALTED_BUDGET_EXCEEDED
    assert "Circuit breaker tripped" in result["final_output"] or "safely halted" in result["final_output"]
