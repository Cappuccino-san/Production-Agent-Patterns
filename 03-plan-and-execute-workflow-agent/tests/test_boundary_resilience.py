"""Tier 5: Boundary conditions, resilience, concurrency, and error recovery tests."""

import concurrent.futures
import logging
import sqlite3
import pytest
from fastapi.testclient import TestClient

from app.agent.graph import build_plan_execute_graph
from app.agent.mock_llm import DeterministicMockLLM
from app.agent.state import PlanExecuteState
from app.database import create_plan_sync, get_plan_sync, search_steps_sync


@pytest.mark.boundary
class TestFTS5SearchHostileInputs:
    """Resilience tests for FTS5 full-text queries with hostile and edge-case inputs."""

    @pytest.mark.parametrize(
        "query",
        [
            "",
            "   ",
            "***",
            "???",
            ":;;<>>>",
            '"unclosed quote',
            "' OR 1=1 --",
            "'; DROP TABLE plans; --",
            "AND",
            "OR",
            "NOT",
            "NEAR",
            "AND OR NOT",
            "café",
            "🚀🔥💻",
            "a" * 200,
            "nonexistent_term_987654321",
        ],
    )
    def test_search_hostile_query_safety(
        self,
        test_client: TestClient,
        sample_seeded_plan: dict,
        query: str,
    ) -> None:
        if not query.strip():
            # FastAPI query validation min_length=1 rejects empty or whitespace query
            resp = test_client.get(f"/api/v1/plans/search?q={query}")
            assert resp.status_code in (200, 422)
        else:
            resp = test_client.get(f"/api/v1/plans/search?q={query}")
            assert resp.status_code == 200
            assert isinstance(resp.json(), list)


@pytest.mark.boundary
class TestReplanningAndRecursionBounds:
    """Validation of adaptive replanning under repeated failures and cycle limits."""

    def test_agent_terminates_gracefully_on_max_iterations(self) -> None:
        # Mock that always fails every step
        always_failing_mock = DeterministicMockLLM(fail_at_step=0)
        graph = build_plan_execute_graph(always_failing_mock)

        state: PlanExecuteState = {
            "goal": "Unattainable goal with persistent failures",
            "plan": [{"title": "Always Failing Step", "description": "trigger_error", "tool": "code"}],
            "max_iterations": 6,
        }

        final_state = graph.invoke(state)
        # Must terminate without infinite loop and have response synthesized
        assert final_state["iterations"] >= 4
        assert final_state["response"] is not None
        assert "Workflow Summary" in final_state["response"]

    def test_replan_bound_halts_infinite_replanning(self) -> None:
        always_failing_mock = DeterministicMockLLM(fail_at_step=0)
        graph = build_plan_execute_graph(always_failing_mock)

        state: PlanExecuteState = {
            "goal": "Infinite replan trap",
            "plan": [{"title": "Failing Step", "description": "trigger_error", "tool": "code"}],
            "replan_count": 3,  # Already at limit
            "needs_replan": True,
            "max_iterations": 15,
        }

        final_state = graph.invoke(state)
        assert final_state["response"] is not None

    def test_replan_execution_recovers_and_updates_database(self, temp_db: str) -> None:
        plan = create_plan_sync(
            goal="Test DB Sync during Replan",
            steps=[
                {"title": "Step 0 (Pass)", "description": "Pass", "tool": "code"},
                {"title": "Step 1 (Fail)", "description": "trigger_error", "tool": "analysis"},
            ],
            db_path=temp_db,
        )

        mock = DeterministicMockLLM()
        graph = build_plan_execute_graph(mock)

        initial_state: PlanExecuteState = {
            "goal": plan["goal"],
            "plan": plan["steps"],
            "current_step_index": 0,
            "past_steps": [],
            "plan_id": plan["id"],
            "db_path": temp_db,
            "max_iterations": 10,
        }

        final_state = graph.invoke(initial_state)
        assert final_state["completed"] is True

        # Check DB reflects completed state
        updated = get_plan_sync(plan["id"], temp_db)
        assert updated is not None
        assert updated["status"] == "completed"
        assert updated["final_response"] is not None

        # Verify all steps in DB are marked completed with non-empty results (Defect 1 fix)
        assert len(updated["steps"]) >= 2
        for s in updated["steps"]:
            assert s["status"] == "completed"
            assert s["result"] is not None
            assert len(s["result"]) > 0

        # Verify FTS5 indexed the recovery step deliverable
        search_results = search_steps_sync("Diagnose", temp_db)
        assert len(search_results) >= 1
        assert any("Diagnose and Recover" in r["title"] for r in search_results)

    def test_truncated_execution_reports_failure_not_completed(self, temp_db: str) -> None:
        """Verify truncated execution when iterations >= max_iterations returns failed/completed=False (Defect 2 fix)."""
        plan = create_plan_sync(
            goal="Four step pipeline that will be truncated",
            steps=[
                {"title": "Step 0", "description": "Pass 0", "tool": "code"},
                {"title": "Step 1", "description": "Pass 1", "tool": "code"},
                {"title": "Step 2", "description": "Pass 2", "tool": "code"},
                {"title": "Step 3", "description": "Pass 3", "tool": "code"},
            ],
            db_path=temp_db,
        )

        mock = DeterministicMockLLM()
        graph = build_plan_execute_graph(mock)

        initial_state: PlanExecuteState = {
            "goal": plan["goal"],
            "plan": plan["steps"],
            "current_step_index": 0,
            "past_steps": [],
            "plan_id": plan["id"],
            "db_path": temp_db,
            "max_iterations": 2,  # Truncate before steps 2 and 3 run
        }

        final_state = graph.invoke(initial_state)
        assert final_state["completed"] is False

        # Check DB reflects failed status and pending steps
        updated = get_plan_sync(plan["id"], temp_db)
        assert updated is not None
        assert updated["status"] == "failed"
        pending_steps = [s for s in updated["steps"] if s["status"] == "pending"]
        assert len(pending_steps) >= 2

    def test_allow_replanning_false_halts_and_routes_to_synthesizer(self, temp_db: str) -> None:
        """Verify allow_replanning=False suppresses replanner and marks workflow failed (Defect 3 fix)."""
        plan = create_plan_sync(
            goal="Pipeline with failure where replanning is disabled",
            steps=[
                {"title": "Step 0", "description": "trigger_error in step 0", "tool": "analysis"},
                {"title": "Step 1", "description": "Should remain pending", "tool": "code"},
            ],
            db_path=temp_db,
        )

        mock = DeterministicMockLLM()
        graph = build_plan_execute_graph(mock)

        initial_state: PlanExecuteState = {
            "goal": plan["goal"],
            "plan": plan["steps"],
            "current_step_index": 0,
            "past_steps": [],
            "plan_id": plan["id"],
            "db_path": temp_db,
            "allow_replanning": False,
            "max_iterations": 10,
        }

        final_state = graph.invoke(initial_state)
        assert final_state["completed"] is False
        assert final_state.get("replan_count", 0) == 0

        # In DB, step 0 must be failed and step 1 pending; no recovery steps inserted
        updated = get_plan_sync(plan["id"], temp_db)
        assert updated is not None
        assert updated["status"] == "failed"
        assert updated["steps"][0]["status"] == "failed"
        assert updated["steps"][1]["status"] == "pending"
        assert not any("Diagnose and Recover" in s["title"] for s in updated["steps"])

    def test_allow_replanning_api_endpoint(self, test_client: TestClient, temp_db: str) -> None:
        """Test API endpoint execution with allow_replanning=False via HTTP."""
        res = test_client.post("/api/v1/plans", json={"goal": "Docker deployment and pipeline setup"})
        assert res.status_code == 201
        plan_id = res.json()["id"]

        with sqlite3.connect(temp_db) as conn:
            conn.execute(
                "UPDATE plan_steps SET description = ? WHERE plan_id = ? AND step_index = 0",
                ("trigger_error in docker", plan_id),
            )
            conn.commit()

        exec_res = test_client.post(
            f"/api/v1/plans/{plan_id}/execute",
            json={"allow_replanning": False},
        )
        assert exec_res.status_code == 200
        data = exec_res.json()
        assert data["completed"] is False
        assert data["status"] == "failed"
        assert data["steps"][0]["status"] == "failed"
        assert not any("Diagnose and Recover" in s["title"] for s in data["steps"])

    def test_persistence_error_logging_in_node_handlers(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test that database persistence errors are logged properly instead of silently swallowed (Defect 4 fix)."""
        caplog.set_level(logging.ERROR)

        plan_steps = [
            {"id": "step_test_invalid", "title": "Step 0", "description": "Pass", "tool": "code", "step_index": 0}
        ]
        invalid_state: PlanExecuteState = {
            "goal": "Test db error logging",
            "plan": plan_steps,
            "current_step_index": 0,
            "past_steps": [],
            "plan_id": "plan_test_invalid",
            "db_path": "/invalid/nonexistent/directory/unwritable.db",
            "max_iterations": 5,
        }

        mock = DeterministicMockLLM()
        graph = build_plan_execute_graph(mock)
        final_state = graph.invoke(invalid_state)

        # Should complete execution without raising uncaught exception, but log errors
        assert final_state["response"] is not None
        assert any(
            "Failed to persist" in record.message or "Failed to update" in record.message
            for record in caplog.records
        )


@pytest.mark.boundary
class TestSQLiteWALConcurrency:
    """Stress test verifying concurrent read and write operations under SQLite WAL mode."""

    def test_concurrent_plan_writes_and_reads(self, temp_db: str) -> None:
        def worker_task(worker_id: int) -> int:
            created = create_plan_sync(
                goal=f"Worker {worker_id} goal for concurrent test",
                steps=[
                    {"title": f"Step W{worker_id}-1", "description": "Work 1", "tool": "code"},
                    {"title": f"Step W{worker_id}-2", "description": "Work 2", "tool": "eval"},
                ],
                db_path=temp_db,
            )
            # Read plan back
            fetched = get_plan_sync(created["id"], temp_db)
            assert fetched is not None
            # Search steps
            results = search_steps_sync(f"W{worker_id}", temp_db)
            return len(results)

        # Execute 10 threads concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(worker_task, i) for i in range(10)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        assert len(results) == 10
        assert all(r >= 1 for r in results)
