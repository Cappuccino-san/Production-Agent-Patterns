"""LangGraph node handlers for drafting, serializing, gating, and executing high-stakes actions."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from app.agent.mock_llm import DeterministicMockLLM
from app.agent.state import HITLGateState
from app.database import save_gate_action_sync, save_gate_audit_sync
from app.models import GateActionRecord, GateAuditLog, GateStatus


class HITLGateExecutor:
    def __init__(self, db_path: str, mock_llm: DeterministicMockLLM, timeout_hours: int = 72) -> None:
        self.db_path = db_path
        self.mock_llm = mock_llm
        self.timeout_hours = timeout_hours

    def draft_node(self, state: HITLGateState) -> dict[str, Any]:
        """Draft high-stakes action, set 3-day SLA timeout, generate Slack blocks."""
        action_id = state["action_id"]
        action_type = state["action_type"]
        description = state["description"]
        payload = state.get("payload", {})

        risk_score = state.get("risk_score") or self.mock_llm.evaluate_risk(action_type, payload)
        now = datetime.now(timezone.utc)
        expires_at = (now + timedelta(hours=self.timeout_hours)).isoformat()
        now_iso = now.isoformat()

        slack_blocks = self.mock_llm.generate_slack_blocks(
            action_id=action_id,
            action_type=action_type,
            risk_score=risk_score,
            description=description,
        )

        return {
            "risk_score": risk_score,
            "status": GateStatus.PENDING_APPROVAL,
            "expires_at": expires_at,
            "created_at": now_iso,
            "updated_at": now_iso,
            "slack_blocks": slack_blocks,
        }

    def serialize_gate_node(self, state: HITLGateState) -> dict[str, Any]:
        """Serialize draft state into SQLite WAL to await asynchronous Slack webhook approval."""
        record = GateActionRecord(
            action_id=state["action_id"],
            action_type=state["action_type"],
            status=state["status"],
            risk_score=state["risk_score"],
            description=state["description"],
            payload=state.get("payload", {}),
            expires_at=state["expires_at"],
            created_at=state["created_at"],
            updated_at=state["updated_at"],
            approver_id=state.get("approver_id"),
            decision_reason=state.get("decision_reason"),
            execution_result=state.get("execution_result"),
        )
        save_gate_action_sync(self.db_path, record)

        audit = GateAuditLog(
            audit_id=f"aud-{uuid.uuid4().hex[:8]}",
            action_id=state["action_id"],
            decision="DRAFT_GATE_ENTERED",
            approver_id="system_gatekeeper",
            note=f"Action drafted with 3-day SLA window expiring at {state['expires_at']}",
        )
        save_gate_audit_sync(self.db_path, audit)

        return {"audit_trail": [audit.model_dump()]}

    def execute_node(self, state: HITLGateState) -> dict[str, Any]:
        """Executes the high-stakes action upon verified human approval."""
        now_iso = datetime.now(timezone.utc).isoformat()
        execution_output = {
            "action_id": state["action_id"],
            "target_system": state["target_system"],
            "status": "APPLIED_SUCCESSFULLY",
            "executed_at": now_iso,
            "executed_by": state.get("approver_id", "slack_user"),
        }

        record = GateActionRecord(
            action_id=state["action_id"],
            action_type=state["action_type"],
            status=GateStatus.APPROVED,
            risk_score=state["risk_score"],
            description=state["description"],
            payload=state.get("payload", {}),
            expires_at=state["expires_at"],
            created_at=state["created_at"],
            updated_at=now_iso,
            approver_id=state.get("approver_id"),
            decision_reason=state.get("decision_reason"),
            execution_result=execution_output,
        )
        save_gate_action_sync(self.db_path, record)

        audit = GateAuditLog(
            audit_id=f"aud-{uuid.uuid4().hex[:8]}",
            action_id=state["action_id"],
            decision="APPROVED_AND_EXECUTED",
            approver_id=state.get("approver_id", "slack_user"),
            note=state.get("decision_reason") or "Approved via Slack webhook interactive button",
        )
        save_gate_audit_sync(self.db_path, audit)

        return {
            "status": GateStatus.APPROVED,
            "updated_at": now_iso,
            "execution_result": execution_output,
            "audit_trail": [audit.model_dump()],
        }

    def abort_node(self, state: HITLGateState) -> dict[str, Any]:
        """Aborts action if rejected by human approver or expired."""
        now_iso = datetime.now(timezone.utc).isoformat()
        is_expired = state.get("decision") == "timeout"
        final_status = GateStatus.EXPIRED if is_expired else GateStatus.REJECTED

        record = GateActionRecord(
            action_id=state["action_id"],
            action_type=state["action_type"],
            status=final_status,
            risk_score=state["risk_score"],
            description=state["description"],
            payload=state.get("payload", {}),
            expires_at=state["expires_at"],
            created_at=state["created_at"],
            updated_at=now_iso,
            approver_id=state.get("approver_id"),
            decision_reason=state.get("decision_reason"),
            execution_result={"aborted": True, "reason": state.get("decision_reason")},
        )
        save_gate_action_sync(self.db_path, record)

        audit = GateAuditLog(
            audit_id=f"aud-{uuid.uuid4().hex[:8]}",
            action_id=state["action_id"],
            decision=final_status.value,
            approver_id=state.get("approver_id", "system"),
            note=state.get("decision_reason") or "Action rejected or timed out",
        )
        save_gate_audit_sync(self.db_path, audit)

        return {
            "status": final_status,
            "updated_at": now_iso,
            "execution_result": {"aborted": True, "reason": state.get("decision_reason")},
            "audit_trail": [audit.model_dump()],
        }
