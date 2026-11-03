"""Tier 2: LangGraph StateGraph execution, node transitions, checkpoint interrupts, and resumption."""

from app.agent.graph import create_approval_graph, resume_graph_with_decision, submit_action_to_graph
from app.agent.mock_llm import DeterministicMockLLM
from app.agent.nodes import (
    approval_gate_node,
    audit_node,
    execution_node,
    rejection_node,
    route_after_gate,
    route_after_triage,
    triage_node,
)
from app.agent.state import ApprovalAgentState
from app.database import SqliteCheckpointer


class TestMockLLMRules:
    """Validate deterministic mock LLM risk classifier and action simulation."""

    def test_risk_classification_categories(self, mock_llm: DeterministicMockLLM):
        assert mock_llm.classify_risk("query_database", "Read user count", {}) == "LOW"
        assert mock_llm.classify_risk("get_user", "Fetch profile", {}) == "LOW"
        assert mock_llm.classify_risk("update_user_email", "Change email address", {}) == "MEDIUM"
        assert mock_llm.classify_risk("modify_record", "Update config flag", {}) == "MEDIUM"
        assert mock_llm.classify_risk("delete_user", "Delete user record", {}) == "HIGH"
        assert mock_llm.classify_risk("truncate_table", "Clear table data", {}) == "HIGH"
        assert mock_llm.classify_risk("drop_database", "Drop database cluster", {}) == "CRITICAL"
        assert mock_llm.classify_risk("terminate_ec2_instances", "Shutdown nodes", {}) == "CRITICAL"

    def test_financial_threshold_classification(self, mock_llm: DeterministicMockLLM):
        assert mock_llm.classify_risk("transfer_funds", "Small bonus", {"amount": 200}) == "MEDIUM"
        assert mock_llm.classify_risk("transfer_funds", "Mid transaction", {"amount": 2500}) == "HIGH"
        assert mock_llm.classify_risk("transfer_funds", "Large transaction", {"amount": 10000}) == "CRITICAL"

    def test_risk_override_precedence(self, mock_llm: DeterministicMockLLM):
        # Even if action looks like a query, override forces CRITICAL
        res = mock_llm.classify_risk("query_database", "Audit query", {}, risk_override="CRITICAL")
        assert res == "CRITICAL"

    def test_safety_plan_formulation(self, mock_llm: DeterministicMockLLM):
        plan_low = mock_llm.formulate_safety_plan("query_database", "LOW", {})
        assert plan_low["requires_review"] is False

        plan_high = mock_llm.formulate_safety_plan("drop_table", "CRITICAL", {"target": "prod"})
        assert plan_high["requires_review"] is True
        assert "CRITICAL" in plan_high["summary"]


class TestIndividualNodes:
    """Validate individual LangGraph node handlers."""

    def test_triage_node_low_risk(self):
        state: ApprovalAgentState = {
            "thread_id": "th_1",
            "request_id": "req_1",
            "action_type": "query_database",
            "description": "Select users",
            "payload": {"query": "SELECT * FROM users"},
            "risk_level": "",
            "status": "init",
            "decision": None,
            "decision_reason": None,
            "decision_by": None,
            "modified_payload": None,
            "result": None,
            "execution_logs": [],
            "created_at": "2026-11-02T12:00:00Z",
            "completed_at": None,
        }
        res = triage_node(state)
        assert res["risk_level"] == "LOW"
        assert res["status"] == "auto_approved"
        assert res["decision"] == "approve"
        assert len(res["execution_logs"]) == 1

    def test_triage_node_high_risk(self):
        state: ApprovalAgentState = {
            "thread_id": "th_2",
            "request_id": "req_2",
            "action_type": "drop_table",
            "description": "Drop table orders",
            "payload": {"table": "orders"},
            "risk_level": "",
            "status": "init",
            "decision": None,
            "decision_reason": None,
            "decision_by": None,
            "modified_payload": None,
            "result": None,
            "execution_logs": [],
            "created_at": "2026-11-02T12:00:00Z",
            "completed_at": None,
        }
        res = triage_node(state)
        assert res["risk_level"] in ("HIGH", "CRITICAL")
        assert res["status"] == "pending_approval"
        assert "Execution halted" in res["execution_logs"][0]

    def test_approval_gate_node_logging(self):
        state: ApprovalAgentState = {
            "thread_id": "th_3",
            "request_id": "req_3",
            "action_type": "update_user",
            "description": "Update name",
            "payload": {"name": "Bob"},
            "risk_level": "MEDIUM",
            "status": "pending_approval",
            "decision": "approve",
            "decision_reason": "Verified ID",
            "decision_by": "alice",
            "modified_payload": None,
            "result": None,
            "execution_logs": [],
            "created_at": "2026-11-02T12:00:00Z",
            "completed_at": None,
        }
        res = approval_gate_node(state)
        assert "alice" in res["execution_logs"][0]
        assert "Verified ID" in res["execution_logs"][0]

    def test_execution_node_with_original_payload(self):
        state: ApprovalAgentState = {
            "thread_id": "th_4",
            "request_id": "req_4",
            "action_type": "update_user",
            "description": "Update user email",
            "payload": {"id": "user_42", "email": "new@example.com"},
            "risk_level": "MEDIUM",
            "status": "approved",
            "decision": "approve",
            "decision_reason": "Authorized",
            "decision_by": "operator",
            "modified_payload": None,
            "result": None,
            "execution_logs": [],
            "created_at": "2026-11-02T12:00:00Z",
            "completed_at": None,
        }
        res = execution_node(state)
        assert res["status"] == "completed"
        assert "user_42" in res["result"]

    def test_execution_node_with_modified_payload(self):
        state: ApprovalAgentState = {
            "thread_id": "th_5",
            "request_id": "req_5",
            "action_type": "update_user",
            "description": "Update user config",
            "payload": {"id": "user_42", "quota": 1000},
            "risk_level": "MEDIUM",
            "status": "modified",
            "decision": "modify",
            "decision_reason": "Reduced quota to 500",
            "decision_by": "operator",
            "modified_payload": {"id": "user_42", "quota": 500},
            "result": None,
            "execution_logs": [],
            "created_at": "2026-11-02T12:00:00Z",
            "completed_at": None,
        }
        res = execution_node(state)
        assert res["status"] == "completed"
        assert res["payload"]["quota"] == 500

    def test_rejection_node(self):
        state: ApprovalAgentState = {
            "thread_id": "th_6",
            "request_id": "req_6",
            "action_type": "drop_database",
            "description": "Drop db",
            "payload": {"db": "analytics"},
            "risk_level": "CRITICAL",
            "status": "rejected",
            "decision": "reject",
            "decision_reason": "Unsafe in production",
            "decision_by": "lead_architect",
            "modified_payload": None,
            "result": None,
            "execution_logs": [],
            "created_at": "2026-11-02T12:00:00Z",
            "completed_at": None,
        }
        res = rejection_node(state)
        assert res["status"] == "rejected"
        assert "Unsafe in production" in res["result"]

    def test_audit_node(self):
        state: ApprovalAgentState = {
            "thread_id": "th_7",
            "request_id": "req_7",
            "action_type": "query_database",
            "description": "Query",
            "payload": {},
            "risk_level": "LOW",
            "status": "completed",
            "decision": "approve",
            "decision_reason": None,
            "decision_by": None,
            "modified_payload": None,
            "result": "Success",
            "execution_logs": [],
            "created_at": "2026-11-02T12:00:00Z",
            "completed_at": None,
        }
        res = audit_node(state)
        assert res["completed_at"] is not None
        assert "Audit finalized" in res["execution_logs"][0]

    def test_routing_functions(self):
        assert route_after_triage({"risk_level": "LOW"}) == "execution_node"
        assert route_after_triage({"risk_level": "HIGH"}) == "approval_gate_node"
        assert route_after_triage({"risk_level": "CRITICAL"}) == "approval_gate_node"

        assert route_after_gate({"decision": "reject"}) == "rejection_node"
        assert route_after_gate({"decision": "approve"}) == "execution_node"
        assert route_after_gate({"decision": "modify"}) == "execution_node"


class TestEndToEndStateGraph:
    """Validate full StateGraph execution paths: auto-approval, pause, approve, reject, modify."""

    def test_auto_approval_low_risk_runs_to_completion(self, checkpointer: SqliteCheckpointer):
        graph = create_approval_graph(checkpointer=checkpointer)
        res = submit_action_to_graph(
            graph=graph,
            thread_id="thread_e2e_low_01",
            request_id="req_e2e_low_01",
            action_type="query_database",
            description="Lookup system parameters",
            payload={"resource": "cluster_info"},
        )
        assert res["next"] == ()
        assert res["values"]["status"] == "completed"
        assert res["values"]["risk_level"] == "LOW"
        assert "cluster_info" in res["values"]["result"]

    def test_high_risk_pauses_at_approval_checkpoint(self, checkpointer: SqliteCheckpointer):
        graph = create_approval_graph(checkpointer=checkpointer)
        res = submit_action_to_graph(
            graph=graph,
            thread_id="thread_e2e_high_01",
            request_id="req_e2e_high_01",
            action_type="terminate_ec2_instances",
            description="Terminate unused sandbox instances",
            payload={"instance_ids": ["i-0123456789"]},
        )
        assert res["next"] == ("approval_gate_node",)
        assert res["values"]["status"] == "pending_approval"
        assert res["values"]["risk_level"] == "CRITICAL"
        assert res["values"]["result"] is None

    def test_resume_with_approval_completes_execution(self, checkpointer: SqliteCheckpointer):
        graph = create_approval_graph(checkpointer=checkpointer)
        thread_id = "thread_e2e_approve_01"
        submit_action_to_graph(
            graph=graph,
            thread_id=thread_id,
            request_id="req_e2e_app_01",
            action_type="drop_table",
            description="Drop obsolete logs table",
            payload={"table": "old_logs"},
        )

        res = resume_graph_with_decision(
            graph=graph,
            thread_id=thread_id,
            decision="approve",
            decision_by="admin_sarah",
            decision_reason="Backup verified and approved",
        )
        assert res["next"] == ()
        assert res["values"]["status"] == "completed"
        assert "drop_table" in res["values"]["result"]
        assert "Authorized by admin_sarah" in res["values"]["result"]

    def test_resume_with_rejection_bypasses_execution(self, checkpointer: SqliteCheckpointer):
        graph = create_approval_graph(checkpointer=checkpointer)
        thread_id = "thread_e2e_reject_01"
        submit_action_to_graph(
            graph=graph,
            thread_id=thread_id,
            request_id="req_e2e_rej_01",
            action_type="delete_all_records",
            description="Purge tenant records",
            payload={"tenant_id": "t-100"},
        )

        res = resume_graph_with_decision(
            graph=graph,
            thread_id=thread_id,
            decision="reject",
            decision_by="sec_officer",
            decision_reason="GDPR retention lock active",
        )
        assert res["next"] == ()
        assert res["values"]["status"] == "rejected"
        assert "cancelled by reviewer sec_officer" in res["values"]["result"]
        assert "GDPR retention lock active" in res["values"]["result"]

    def test_resume_with_modify_executes_adjusted_payload(self, checkpointer: SqliteCheckpointer):
        graph = create_approval_graph(checkpointer=checkpointer)
        thread_id = "thread_e2e_modify_01"
        submit_action_to_graph(
            graph=graph,
            thread_id=thread_id,
            request_id="req_e2e_mod_01",
            action_type="update_user",
            description="Update user quota",
            payload={"id": "user_10", "quota_limit": 100000},
        )

        res = resume_graph_with_decision(
            graph=graph,
            thread_id=thread_id,
            decision="modify",
            decision_by="finance_lead",
            decision_reason="Cap quota at 5000",
            modified_payload={"id": "user_10", "quota_limit": 5000},
        )
        assert res["next"] == ()
        assert res["values"]["status"] == "completed"
        assert res["values"]["payload"]["quota_limit"] == 5000
        assert "quota_limit" in res["values"]["result"]
