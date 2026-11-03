"""Tier 2: LangGraph State Machine Drafting and Webhook Resumption Tests."""

import pytest
from app.agent.graph import create_draft_graph, create_resume_graph
from app.agent.mock_llm import DeterministicMockLLM
from app.models import ActionType, GateStatus


class TestAgentGraph:
    def test_draft_graph_serialization(self, temp_db: str, mock_llm: DeterministicMockLLM):
        draft_graph = create_draft_graph(temp_db, mock_llm, timeout_hours=72)

        state = {
            "action_id": "act-test-draft-1",
            "action_type": ActionType.DATABASE_MIGRATION,
            "description": "Drop legacy indexes and partition user_activity table",
            "target_system": "aurora-postgres-primary",
            "risk_score": 90.0,
            "payload": {"tables": ["user_activity"]},
            "status": GateStatus.DRAFTED,
            "expires_at": "",
            "created_at": "",
            "updated_at": "",
            "approver_id": None,
            "decision": None,
            "decision_reason": None,
            "execution_result": None,
            "slack_blocks": None,
            "audit_trail": [],
        }

        result = draft_graph.invoke(state)

        assert result["status"] == GateStatus.PENDING_APPROVAL
        assert result["expires_at"] != ""
        assert result["slack_blocks"] is not None
        assert result["slack_blocks"]["channel"] == "#prod-gatekeepers"

    def test_resume_graph_approval_execution(self, temp_db: str, mock_llm: DeterministicMockLLM):
        resume_graph = create_resume_graph(temp_db, mock_llm)

        state = {
            "action_id": "act-test-resume-1",
            "action_type": ActionType.DEPLOY_PRODUCTION,
            "description": "Deploy emergency hotfix for auth token leak",
            "target_system": "api-gateway",
            "risk_score": 80.0,
            "payload": {"hotfix_id": "HF-909"},
            "status": GateStatus.PENDING_APPROVAL,
            "expires_at": "2099-01-01T00:00:00Z",
            "created_at": "2026-11-02T12:00:00Z",
            "updated_at": "2026-11-02T12:00:00Z",
            "approver_id": "U_ENG_LEAD",
            "decision": "approve",
            "decision_reason": "Hotfix peer-reviewed and tested",
            "execution_result": None,
            "slack_blocks": None,
            "audit_trail": [],
        }

        result = resume_graph.invoke(state)
        assert result["status"] == GateStatus.APPROVED
        assert result["execution_result"]["status"] == "APPLIED_SUCCESSFULLY"

    def test_resume_graph_rejection_abort(self, temp_db: str, mock_llm: DeterministicMockLLM):
        resume_graph = create_resume_graph(temp_db, mock_llm)

        state = {
            "action_id": "act-test-resume-2",
            "action_type": ActionType.MASS_REFUND,
            "description": "Refund 500 accounts totaling $25,000",
            "target_system": "stripe-billing-gateway",
            "risk_score": 95.0,
            "payload": {"total_usd": 25000},
            "status": GateStatus.PENDING_APPROVAL,
            "expires_at": "2099-01-01T00:00:00Z",
            "created_at": "2026-11-02T12:00:00Z",
            "updated_at": "2026-11-02T12:00:00Z",
            "approver_id": "U_CFO",
            "decision": "reject",
            "decision_reason": "Financial audit pending confirmation",
            "execution_result": None,
            "slack_blocks": None,
            "audit_trail": [],
        }

        result = resume_graph.invoke(state)
        assert result["status"] == GateStatus.REJECTED
        assert result["execution_result"]["aborted"] is True
