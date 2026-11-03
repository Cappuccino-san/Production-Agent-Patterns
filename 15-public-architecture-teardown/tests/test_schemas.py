"""Unit tests for Pydantic models, teardown schemas, and benchmark metrics."""

import pytest
from pydantic import ValidationError
from app.models import (
    AgentQueryRequest,
    AgentQueryResponse,
    BenchmarkMetric,
    TeardownDeepDive,
)


def test_teardown_deep_dive_schema():
    dd = TeardownDeepDive(
        slug="test-slug",
        title="Test Deep Dive Title",
        category="Architecture",
        summary="Short summary of deep dive for testing",
        content_markdown="# Heading\nDetailed teardown text.",
        key_findings=["Finding 1", "Finding 2"],
        read_time_minutes=10,
    )
    assert dd.slug == "test-slug"
    assert len(dd.key_findings) == 2


def test_benchmark_metric_schema():
    bm = BenchmarkMetric(
        repository_id="01",
        architecture_pattern="Prompt-to-Code ReAct Agent",
        avg_latency_ms=120.0,
        cost_per_1k_tasks_usd=8.50,
        resilience_score=96,
    )
    assert bm.repository_id == "01"
    assert bm.resilience_score == 96


def test_agent_query_request_validation():
    with pytest.raises(ValidationError):
        AgentQueryRequest(query="hi")  # min_length 3

    valid = AgentQueryRequest(query="How does the cost kill-switch work?")
    assert "cost" in valid.query
