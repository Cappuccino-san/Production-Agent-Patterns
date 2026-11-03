"""Tests for FastAPI HTTP API endpoints in Shadow Trajectory Comparator."""

import pytest


def test_health_check(client):
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["service"] == "shadow-trajectory-comparator"


def test_execute_with_forced_shadow(client):
    payload = {
        "prompt": "Evaluate container orchestration security baselines",
        "force_shadow": True,
    }
    res = client.post("/comparator/execute", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["request_id"].startswith("req-")
    assert data["is_shadow_sampled"] is True
    assert data["shadow_comparison_id"] is not None
    assert data["primary_cost_usd"] > 0


def test_list_comparisons(client):
    # Ensure at least one shadow run
    payload = {
        "prompt": "Inspect database sharding bottlenecks",
        "force_shadow": True,
    }
    client.post("/comparator/execute", json=payload)

    list_res = client.get("/comparator/comparisons")
    assert list_res.status_code == 200
    comps = list_res.json()
    assert len(comps) >= 1
    assert "primary_trajectory" in comps[0]
    assert "candidate_trajectory" in comps[0]


def test_get_comparison_by_id(client):
    payload = {
        "prompt": "Trace memory leak patterns in asynchronous workers",
        "force_shadow": True,
    }
    exec_res = client.post("/comparator/execute", json=payload)
    cmp_id = exec_res.json()["shadow_comparison_id"]

    detail_res = client.get(f"/comparator/{cmp_id}")
    assert detail_res.status_code == 200
    data = detail_res.json()
    assert data["comparison_id"] == cmp_id
    assert "diff_summary" in data


def test_fts5_search_endpoint(client):
    payload = {
        "prompt": "Biometric cryptographic signature validation",
        "force_shadow": True,
    }
    client.post("/comparator/execute", json=payload)

    search_res = client.get("/comparator/search?q=Biometric")
    assert search_res.status_code == 200
    hits = search_res.json()
    assert len(hits) >= 1
