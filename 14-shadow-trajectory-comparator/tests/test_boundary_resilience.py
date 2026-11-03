"""Tests for boundary conditions, validation, and RFC7807 error responses."""

import pytest


def test_missing_comparison_returns_404_rfc7807(client):
    res = client.get("/comparator/non-existent-cmp-999")
    assert res.status_code == 404
    data = res.json()
    assert data["status"] == 404
    assert "not found" in data["detail"].lower()


def test_invalid_payload_returns_422_rfc7807(client):
    # Prompt too short
    res = client.post("/comparator/execute", json={"prompt": "hi"})
    assert res.status_code == 422
    data = res.json()
    assert data["status"] == 422
    assert "Validation Error" in data["title"]


def test_fts5_special_characters_resilience(client):
    res = client.get("/comparator/search?q=***((--!!''\"\"")
    assert res.status_code == 200
    hits = res.json()
    assert isinstance(hits, list)
