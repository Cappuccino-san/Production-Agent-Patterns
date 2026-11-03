"""Tier 4: FastAPI REST API Contracts and Endpoint Verification."""

import pytest
from fastapi.testclient import TestClient


class TestApiContracts:
    def test_health_endpoints(self, test_client: TestClient):
        r_live = test_client.get("/health/live")
        assert r_live.status_code == 200
        assert r_live.json() == {"status": "alive"}

        r_ready = test_client.get("/health/ready")
        assert r_ready.status_code == 200
        assert r_ready.json()["status"] == "ready"

    def test_evaluate_endpoint_golden_pass(self, test_client: TestClient):
        payload = {
            "dag_id": "golden-default",
            "pr_number": 42,
            "commit_sha": "abc1234",
            "trajectories": [
                {
                    "trajectory_id": "t-1",
                    "pr_number": 42,
                    "commit_sha": "abc1234",
                    "tool_call_sequence": [
                        "checkout_branch",
                        "run_static_analysis",
                        "compile_code",
                        "run_unit_tests",
                        "report_results",
                    ],
                }
            ],
        }
        resp = test_client.post("/ci/evaluate", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["verdict"] == "PASS"
        assert data["passed_count"] == 1
        assert data["failed_count"] == 0

    def test_evaluate_endpoint_deviation_blocks_pr(self, test_client: TestClient):
        payload = {
            "dag_id": "golden-default",
            "pr_number": 43,
            "commit_sha": "bad5678",
            "trajectories": [
                {
                    "trajectory_id": "t-bad",
                    "pr_number": 43,
                    "commit_sha": "bad5678",
                    "tool_call_sequence": [
                        "checkout_branch",
                        "report_results",  # Skipped static analysis, compilation, tests
                    ],
                }
            ],
        }
        resp = test_client.post("/ci/evaluate", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["verdict"] == "BLOCK"
        assert data["failed_count"] == 1
        assert len(data["deviations"]) == 1

    def test_get_evaluation_not_found_returns_rfc7807(self, test_client: TestClient):
        resp = test_client.get("/ci/evals/eval-nonexistent-999")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()
