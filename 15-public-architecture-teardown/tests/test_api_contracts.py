"""Tests for FastAPI HTTP API endpoints in Public Architecture Teardown."""

import pytest


def test_health_check(client):
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["service"] == "public-architecture-teardown"


def test_list_teardowns_endpoint(client):
    res = client.get("/teardowns")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 3
    assert data[0]["slug"] == "swarm-topology-state-machine-design"


def test_list_benchmarks_endpoint(client):
    res = client.get("/teardowns/benchmarks")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 15
    assert data[0]["architecture_pattern"] == "Prompt-to-Code ReAct Agent"


def test_get_single_teardown_by_slug(client):
    res = client.get("/teardowns/cost-kill-switch-shadow-comparator")
    assert res.status_code == 200
    data = res.json()
    assert "Real-Time Cost Kill-Switches" in data["title"]
    assert len(data["key_findings"]) >= 3


def test_search_teardowns_fts5(client):
    res = client.get("/teardowns/search?q=kill-switch")
    assert res.status_code == 200
    hits = res.json()
    assert len(hits) >= 1
    assert "cost-kill-switch" in hits[0]["slug"]


def test_query_teardown_agent(client):
    payload = {"query": "Explain how the sandbox prevents socket exfiltration"}
    res = client.post("/teardowns/query-agent", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "query_id" in data
    assert "Zero-Egress Sandboxing" in data["answer"] or "Inter-Agent Security" in data["answer"]
    assert len(data["sources"]) >= 1
