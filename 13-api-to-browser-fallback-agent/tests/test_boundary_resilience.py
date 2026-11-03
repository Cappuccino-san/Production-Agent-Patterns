"""Tests for edge cases, validation boundaries, and RFC7807 error responses."""

import pytest


def test_missing_execution_returns_404_rfc7807(client):
    res = client.get("/fallback/non-existent-exec-id")
    assert res.status_code == 404
    data = res.json()
    assert data["status"] == 404
    assert "not found" in data["detail"].lower()


def test_validation_error_rfc7807(client):
    # target_id empty or too short
    res = client.post("/fallback/execute", json={"target_id": "a"})
    assert res.status_code == 422
    data = res.json()
    assert data["status"] == 422
    assert "Validation Error" in data["title"]


def test_fts5_special_characters_resilience(client):
    res = client.get("/fallback/search?q=***((--!!''\"\"")
    assert res.status_code == 200
    hits = res.json()
    assert isinstance(hits, list)


def test_execute_workflow_fallback_on_timeout(client):
    payload = {
        "action": "EXPORT_REPORT",
        "target_id": "REP-TIMEOUT-99",
        "simulate_api_failure": True,
        "simulated_failure_type": "timeout",
    }
    res = client.post("/fallback/execute", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["execution_channel"] == "BROWSER_FALLBACK"
    assert data["fallback_triggered"] is True
    assert data["api_status_code"] == 504
