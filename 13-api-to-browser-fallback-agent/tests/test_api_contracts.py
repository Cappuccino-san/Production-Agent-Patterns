"""Tests for FastAPI HTTP API contracts in API-to-Browser Fallback Agent."""

import pytest


def test_health_check(client):
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["service"] == "api-to-browser-fallback-agent"


def test_execute_workflow_api_direct_path(client):
    payload = {
        "action": "FETCH_INVOICE",
        "target_id": "INV-NORMAL-701",
        "api_endpoint": "https://api.internal/v1/invoices",
        "gui_url": "https://portal.internal/invoices",
        "simulate_api_failure": False,
    }
    res = client.post("/fallback/execute", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["execution_id"].startswith("exec-")
    assert data["execution_channel"] == "API"
    assert data["status"] == "COMPLETED_VIA_API"
    assert data["fallback_triggered"] is False
    assert data["api_status_code"] == 200
    assert data["extracted_data"]["source"] == "REST_API_V1"


def test_execute_workflow_fallback_on_404(client):
    payload = {
        "action": "FETCH_INVOICE",
        "target_id": "INV-MISSING-404",
        "api_endpoint": "https://api.internal/v1/invoices",
        "gui_url": "https://portal.internal/invoices",
        "simulate_api_failure": True,
        "simulated_failure_type": "404",
    }
    res = client.post("/fallback/execute", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["execution_channel"] == "BROWSER_FALLBACK"
    assert data["status"] == "COMPLETED_VIA_BROWSER_FALLBACK"
    assert data["fallback_triggered"] is True
    assert data["api_status_code"] == 404
    assert data["browser_session_id"] is not None
    assert data["extracted_data"]["source"] == "HEADLESS_BROWSER_DOM"


def test_get_execution_by_id(client):
    create_payload = {
        "action": "EXTRACT_METRICS",
        "target_id": "METRIC-AUDIT-55",
        "simulate_api_failure": False,
    }
    create_res = client.post("/fallback/execute", json=create_payload)
    exec_id = create_res.json()["execution_id"]

    get_res = client.get(f"/fallback/{exec_id}")
    assert get_res.status_code == 200
    data = get_res.json()
    assert data["execution_id"] == exec_id
    assert len(data["logs"]) >= 1


def test_search_executions_fts5(client):
    payload = {
        "action": "EXPORT_REPORT",
        "target_id": "FINANCIAL-QUARTERLY-2026",
        "simulate_api_failure": False,
    }
    client.post("/fallback/execute", json=payload)

    search_res = client.get("/fallback/search?q=FINANCIAL")
    assert search_res.status_code == 200
    hits = search_res.json()
    assert len(hits) >= 1
