"""Tests for LangGraph teardown assistant state machine."""

import pytest
from app.agent.graph import build_teardown_agent_graph
from app.agent.state import TeardownAssistantState


def test_graph_cost_kill_switch_query(temp_db_path):
    graph = build_teardown_agent_graph()
    initial_state = TeardownAssistantState(
        query_id="qry-test-01",
        query="Explain how the $0.50 cost kill-switch prevents budget blowouts",
        db_path=temp_db_path,
    )

    result = graph.invoke(initial_state)

    assert "Cost Controls & Trajectory Evaluation" in result["answer"]
    assert "0.50" in result["answer"]
    assert any("Deep Dive 3" in src for src in result["sources"])


def test_graph_security_isolation_query(temp_db_path):
    graph = build_teardown_agent_graph()
    initial_state = TeardownAssistantState(
        query_id="qry-test-02",
        query="How does the sanitization proxy neutralize cross-agent prompt injection?",
        db_path=temp_db_path,
    )

    result = graph.invoke(initial_state)

    assert "Inter-Agent Security & Isolation" in result["answer"]
    assert "Sanitization Proxy" in result["answer"]
    assert any("Deep Dive 2" in src for src in result["sources"])


def test_graph_swarm_topology_query(temp_db_path):
    graph = build_teardown_agent_graph()
    initial_state = TeardownAssistantState(
        query_id="qry-test-03",
        query="Why are strictly typed Pydantic objects required in swarms?",
        db_path=temp_db_path,
    )

    result = graph.invoke(initial_state)

    assert "Swarm Topologies & State Machine Invariants" in result["answer"]
    assert "Pydantic" in result["answer"]
    assert any("Deep Dive 1" in src for src in result["sources"])
