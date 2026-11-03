"""Unit tests for models, schemas, and similarity/cost diff calculations."""

import pytest
from pydantic import ValidationError
from app.agent.comparator import calculate_tool_path_similarity, diff_trajectories
from app.models import (
    AgentTrafficRequest,
    CandidateTopology,
    ComparisonRecommendation,
    ToolCallRecord,
    TrajectorySummary,
)


def test_calculate_tool_path_similarity():
    p = TrajectorySummary(
        topology_name="STANDARD_REACT",
        tool_calls=[
            ToolCallRecord(step_index=1, tool_name="search"),
            ToolCallRecord(step_index=2, tool_name="eval"),
        ],
    )
    c = TrajectorySummary(
        topology_name="PARALLEL_REACT",
        tool_calls=[
            ToolCallRecord(step_index=1, tool_name="search"),
            ToolCallRecord(step_index=2, tool_name="summarize"),
        ],
    )
    # intersection = {search} (1), union = {search, eval, summarize} (3) => 1/3 ~ 0.3333
    sim = calculate_tool_path_similarity(p, c)
    assert 0.33 <= sim <= 0.34


def test_diff_trajectories_recommendation_deploy():
    p = TrajectorySummary(
        topology_name="STANDARD",
        tool_calls=[ToolCallRecord(step_index=1, tool_name="search")],
        cost_usd=0.010,
        latency_ms=100.0,
    )
    # Candidate saves 50% cost and is faster
    c = TrajectorySummary(
        topology_name="CANDIDATE",
        tool_calls=[ToolCallRecord(step_index=1, tool_name="search")],
        cost_usd=0.005,
        latency_ms=60.0,
    )
    report = diff_trajectories("req-1", "test prompt", p, c)
    assert report.cost_savings_pct == 50.0
    assert report.recommendation == ComparisonRecommendation.DEPLOY_CANDIDATE


def test_diff_trajectories_recommendation_reject():
    p = TrajectorySummary(
        topology_name="STANDARD",
        cost_usd=0.010,
        latency_ms=50.0,
    )
    # Candidate costs significantly more
    c = TrajectorySummary(
        topology_name="REGRESSION",
        cost_usd=0.025,
        latency_ms=180.0,
    )
    report = diff_trajectories("req-2", "test prompt", p, c)
    assert report.recommendation == ComparisonRecommendation.REJECT_REGRESSION


def test_agent_traffic_request_validation():
    with pytest.raises(ValidationError):
        AgentTrafficRequest(prompt="x")

    valid = AgentTrafficRequest(prompt="Valid prompt", force_shadow=True)
    assert valid.prompt == "Valid prompt"
    assert valid.force_shadow is True
