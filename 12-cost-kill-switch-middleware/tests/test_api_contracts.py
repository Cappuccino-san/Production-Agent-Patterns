"""Tests for FastAPI HTTP API endpoints in Cost Kill-Switch Middleware."""

import pytest


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "cost-kill-switch-middleware"


def test_pricing_table_endpoint(client):
    response = client.get("/cost/pricing-table")
    assert response.status_code == 200
    data = response.json()
    assert "gpt-4o" in data["pricing_per_1k_tokens"]
    assert data["kill_switch_threshold_usd"] == 0.50


def test_run_agent_normal_flow(client):
    payload = {
        "prompt": "Evaluate market penetration strategy for B2B SaaS",
        "force_spend_spike": False,
        "max_iterations": 2,
    }
    response = client.post("/cost/run-agent", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["request_id"].startswith("cost-")
    assert data["kill_switch_triggered"] is False
    assert data["total_cost_usd"] < 0.50
    assert len(data["ledger"]) == 2


def test_run_agent_spend_spike_kill_switch_engaged(client):
    payload = {
        "prompt": "Trigger recursive code generator benchmark",
        "force_spend_spike": True,
        "max_iterations": 3,
    }
    response = client.post("/cost/run-agent", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["kill_switch_triggered"] is True
    assert data["fallback_engaged"] is True
    assert data["final_model"] == "gpt-4o-mini"
    assert any(entry["kill_switch_active"] is True for entry in data["ledger"])


def test_get_cost_ledger_endpoint(client):
    # First run an agent
    payload = {
        "prompt": "Ledger audit trace verification task",
        "force_spend_spike": False,
        "max_iterations": 1,
    }
    create_res = client.post("/cost/run-agent", json=payload)
    req_id = create_res.json()["request_id"]

    # Now fetch ledger
    fetch_res = client.get(f"/cost/{req_id}")
    assert fetch_res.status_code == 200
    ledger_data = fetch_res.json()
    assert ledger_data["request_id"] == req_id
    assert len(ledger_data["ledger"]) >= 1


def test_fts5_search_endpoint(client):
    payload = {
        "prompt": "Quantum cryptography post-quantum lattice synthesis",
        "force_spend_spike": False,
        "max_iterations": 1,
    }
    client.post("/cost/run-agent", json=payload)

    search_res = client.get("/cost/search?q=cryptography")
    assert search_res.status_code == 200
    hits = search_res.json()
    assert len(hits) >= 1
