"""Tier 5: Boundary conditions, concurrency under WAL mode, and failure recovery resilience tests."""

import concurrent.futures
from fastapi.testclient import TestClient

from app.agent.graph import create_approval_graph, submit_action_to_graph
from app.database import (
    SqliteCheckpointer,
    list_pending_requests_sync,
)


class TestConcurrencyUnderWAL:
    """Validate concurrency without database locking issues using SQLite WAL mode."""

    def test_concurrent_submissions(self, temp_db: str, agent_graph):
        """Execute concurrent action submissions and verify SQLite WAL handling."""
        def run_submission(idx: int):
            thread_id = f"th_concurrent_sub_{idx}"
            req_id = f"req_concurrent_sub_{idx}"
            return submit_action_to_graph(
                graph=agent_graph,
                thread_id=thread_id,
                request_id=req_id,
                action_type="query_database",
                description=f"Concurrent lookup {idx}",
                payload={"worker_id": idx},
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(run_submission, i) for i in range(10)]
            results = [f.result() for f in futures]

        assert len(results) == 10
        for r in results:
            assert r["values"]["status"] == "completed"

    def test_concurrent_decisions(self, temp_db: str, agent_graph):
        """Execute concurrent human decisions and resume workflows under SQLite WAL."""
        threads = [f"th_concurrent_dec_{i}" for i in range(8)]
        for i, tid in enumerate(threads):
            submit_action_to_graph(
                graph=agent_graph,
                thread_id=tid,
                request_id=f"req_concurrent_dec_{i}",
                action_type="terminate_ec2_instances",
                description=f"Teardown node {i}",
                payload={"node_id": i},
            )

        def run_decision(tid: str):
            from app.agent.graph import resume_graph_with_decision

            return resume_graph_with_decision(
                graph=agent_graph,
                thread_id=tid,
                decision="approve",
                decision_by="batch_reviewer",
                decision_reason="Concurrent authorization",
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(run_decision, tid) for tid in threads]
            results = [f.result() for f in futures]

        assert len(results) == 8
        for r in results:
            assert r["values"]["status"] == "completed"
            assert "terminate_ec2_instances" in r["values"]["result"]


class TestDoubleDecisionCollision:
    """Validate double decision prevention and conflict handling."""

    def test_double_decision_attempt_returns_409(self, test_client: TestClient):
        # 1. Submit high-risk request
        res = test_client.post(
            "/api/v1/approvals/submit",
            json={
                "action_type": "drop_table",
                "description": "Drop staging metrics table",
                "payload": {"table": "metrics_stg"},
            },
        )
        req_id = res.json()["id"]

        # 2. First reviewer approves
        first = test_client.post(
            f"/api/v1/approvals/{req_id}/decision",
            json={
                "decision": "approve",
                "decision_by": "reviewer_one",
                "decision_reason": "First signoff",
            },
        )
        assert first.status_code == 200

        # 3. Second reviewer attempts decision on now-finalized request
        second = test_client.post(
            f"/api/v1/approvals/{req_id}/decision",
            json={
                "decision": "reject",
                "decision_by": "reviewer_two",
                "decision_reason": "Second signoff attempt",
            },
        )
        assert second.status_code == 409
        assert "already finalized" in second.json()["detail"].lower()


class TestStateRecoveryAndServerRestart:
    """Validate persistence of thread state across checkpointer re-instantiation."""

    def test_checkpointer_persistence_across_restarts(self, temp_db: str):
        thread_id = "thread_restart_simulation_01"
        req_id = "req_restart_simulation_01"

        # Instance 1: start workflow and interrupt
        chk1 = SqliteCheckpointer(temp_db)
        graph1 = create_approval_graph(checkpointer=chk1)
        submit_action_to_graph(
            graph=graph1,
            thread_id=thread_id,
            request_id=req_id,
            action_type="drop_database",
            description="Drop analytics database",
            payload={"db": "analytics"},
        )

        cfg = {"configurable": {"thread_id": thread_id}}
        st1 = graph1.get_state(cfg)
        assert st1.next == ("approval_gate_node",)

        # Instance 2: simulate server restart using same temp_db
        chk2 = SqliteCheckpointer(temp_db)
        graph2 = create_approval_graph(checkpointer=chk2)
        st2 = graph2.get_state(cfg)

        assert st2.next == ("approval_gate_node",)
        assert st2.values["status"] == "pending_approval"
        assert st2.values["risk_level"] == "CRITICAL"

        # Resume from reloaded state
        from app.agent.graph import resume_graph_with_decision

        resumed = resume_graph_with_decision(
            graph=graph2,
            thread_id=thread_id,
            decision="approve",
            decision_by="ops_recovery_team",
            decision_reason="Post-restart confirmation",
        )
        assert resumed["next"] == ()
        assert resumed["values"]["status"] == "completed"


class TestBoundaryPayloadResilience:
    """Validate complex, large, and unicode payloads."""

    def test_complex_and_unicode_payloads(self, test_client: TestClient):
        complex_payload = {
            "unicode_text": "こんにちは世界 🚀 / 测试 / üñîçødé",
            "nested": {
                "depth_1": {
                    "depth_2": [1, 2, 3, {"flag": True}],
                }
            },
            "array_data": ["item_" + str(i) for i in range(100)],
        }
        res = test_client.post(
            "/api/v1/approvals/submit",
            json={
                "action_type": "query_database",
                "description": "Unicode test query for multilingual logs",
                "payload": complex_payload,
            },
        )
        assert res.status_code == 201
        data = res.json()
        assert data["payload"]["unicode_text"] == complex_payload["unicode_text"]
        assert len(data["payload"]["array_data"]) == 100

    def test_list_pending_when_empty(self, temp_db: str):
        # Database has no pending requests initially
        pending = list_pending_requests_sync(temp_db)
        assert isinstance(pending, list)

    def test_get_nonexistent_thread_state_safely(self, agent_graph):
        cfg = {"configurable": {"thread_id": "thread_does_not_exist_xyz"}}
        st = agent_graph.get_state(cfg)
        # Should have empty values and no next nodes
        assert st.next == ()
        assert st.values == {}
