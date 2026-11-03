"""Tests for boundary conditions, edge cases, and RFC7807 error responses."""

import pytest


def test_missing_record_returns_404_rfc7807(client):
    response = client.get("/cost/non-existent-request-999")
    assert response.status_code == 404
    data = response.json()
    assert data["status"] == 404
    assert "not found" in data["detail"].lower()


def test_invalid_task_payload_validation_rfc7807(client):
    # Prompt too short (< 3 chars)
    response = client.post("/cost/run-agent", json={"prompt": "x"})
    assert response.status_code == 422
    data = response.json()
    assert data["status"] == 422
    assert "Validation Error" in data["title"]


def test_max_iterations_boundary(client):
    # max_iterations > 10 should fail validation
    response = client.post("/cost/run-agent", json={"prompt": "Valid prompt", "max_iterations": 99})
    assert response.status_code == 422


def test_fts5_special_characters_resilience(client):
    # Searching with syntax characters like quotes, asterisks, etc. shouldn't crash
    response = client.get("/cost/search?q='\"OR 1=1;--*()")
    assert response.status_code == 200
    hits = response.json()
    assert isinstance(hits, list)
