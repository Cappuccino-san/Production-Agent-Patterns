"""Tier 5: Boundary Resilience, Concurrency Stress, and Extreme Metrics Tests."""

import concurrent.futures
from fastapi.testclient import TestClient
from app.database import search_agent_spans_fts_sync


class TestBoundaryResilience:
    def test_search_empty_and_special_characters(self, temp_db: str):
        hits_empty = search_agent_spans_fts_sync(temp_db, "   ")
        assert hits_empty == []

        hits_special = search_agent_spans_fts_sync(temp_db, "'; DROP TABLE agent_spans; -- !@#$")
        assert isinstance(hits_special, list)

    def test_concurrent_agent_tracing_wal_resilience(self, test_client: TestClient):
        def run_trace(i: int):
            return test_client.post(
                "/traces/run-agent",
                json={
                    "agent_name": f"WorkerAgent_{i}",
                    "prompt": f"Execute concurrent telemetry benchmark test iteration {i}",
                    "destination_sink": "Arize",
                },
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(run_trace, i) for i in range(5)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        for res in results:
            assert res.status_code == 201
            assert res.json()["sink"] == "Arize"
            assert len(res.json()["spans"]) >= 4
