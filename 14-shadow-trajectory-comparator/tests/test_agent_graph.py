"""Tests for LangGraph shadow comparator workflow."""

import pytest
from app.agent.graph import build_comparator_graph
from app.agent.state import ShadowComparatorState
from app.models import ComparisonRecommendation


def test_graph_without_shadow_sampling():
    graph = build_comparator_graph()
    initial_state = ShadowComparatorState(
        request_id="test-prod-only-001",
        prompt="Synthesize quarterly cloud infrastructure expenditure",
        is_shadow_sampled=False,
    )

    result = graph.invoke(initial_state)

    assert result["primary_trajectory"] is not None
    assert result["primary_trajectory"].topology_name == "STANDARD_REACT"
    assert result.get("candidate_trajectory") is None
    assert result.get("comparison_report") is None


def test_graph_with_shadow_sampling_engaged():
    graph = build_comparator_graph()
    initial_state = ShadowComparatorState(
        request_id="test-shadow-mirror-002",
        prompt="Synthesize quarterly cloud infrastructure expenditure",
        is_shadow_sampled=True,
    )

    result = graph.invoke(initial_state)

    assert result["primary_trajectory"] is not None
    assert result["candidate_trajectory"] is not None
    assert result["candidate_trajectory"].topology_name == "PARALLEL_SPECULATIVE_REACT"
    assert result["comparison_report"] is not None
    report = result["comparison_report"]
    assert report.request_id == "test-shadow-mirror-002"
    assert report.cost_savings_pct > 0
    assert report.recommendation in [
        ComparisonRecommendation.DEPLOY_CANDIDATE,
        ComparisonRecommendation.NEUTRAL,
    ]
