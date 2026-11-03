"""Tests for boundary conditions, missing records, and RFC7807 error responses."""

import pytest


def test_missing_teardown_returns_404_rfc7807(client):
    res = client.get("/teardowns/non-existent-deep-dive-slug")
    assert res.status_code == 404
    data = res.json()
    assert data["status"] == 404
    assert "not found" in data["detail"].lower()


def test_invalid_query_returns_422_rfc7807(client):
    # Query too short
    res = client.post("/teardowns/query-agent", json={"query": "x"})
    assert res.status_code == 422
    data = res.json()
    assert data["status"] == 422
    assert "Validation Error" in data["title"]


def test_fts5_special_characters_resilience(client):
    res = client.get("/teardowns/search?q=***((--!!''\"\"")
    assert res.status_code == 200
    hits = res.json()
    assert isinstance(hits, list)
