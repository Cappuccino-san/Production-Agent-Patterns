"""Node handlers and conditional routing logic for the LangGraph approval workflow."""

from datetime import datetime, timezone
from typing import Any
from app.agent.mock_llm import DeterministicMockLLM
from app.agent.state import ApprovalAgentState

mock_llm = DeterministicMockLLM()


def triage_node(state: ApprovalAgentState) -> dict[str, Any]:
    """Triage incoming request, classify risk, and formulate safety plan."""
    action_type = state["action_type"]
    description = state["description"]
    payload = state.get("payload", {})
    existing_risk = state.get("risk_level")

    # If risk_level was already provided/overridden, preserve it, else classify
    risk = mock_llm.classify_risk(
        action_type=action_type,
        description=description,
        payload=payload,
        risk_override=existing_risk,
    )

    safety_plan = mock_llm.formulate_safety_plan(action_type, risk, payload)

    if risk == "LOW":
        log_entry = f"Action '{action_type}' assessed as LOW risk. Auto-approved for immediate execution."
        return {
            "risk_level": risk,
            "status": "auto_approved",
            "decision": "approve",
            "execution_logs": [log_entry],
        }
    else:
        log_entry = (
            f"Action '{action_type}' assessed as {risk} risk ({safety_plan['summary']}). "
            f"Execution halted at approval checkpoint."
        )
        return {
            "risk_level": risk,
            "status": "pending_approval",
            "execution_logs": [log_entry],
        }


def approval_gate_node(state: ApprovalAgentState) -> dict[str, Any]:
    """Inspect human decision after resuming from checkpoint."""
    decision = state.get("decision", "approve")
    decision_by = state.get("decision_by", "reviewer")
    reason = state.get("decision_reason", "")
    log_entry = f"Human decision rendered: '{decision}' by {decision_by}. Rationale: '{reason}'"
    return {
        "execution_logs": [log_entry],
    }


def execution_node(state: ApprovalAgentState) -> dict[str, Any]:
    """Safely execute the approved or auto-approved tool action."""
    action_type = state["action_type"]
    decision = state.get("decision", "approve")
    is_modified = decision == "modify"
    payload = state.get("modified_payload") if is_modified and state.get("modified_payload") else state.get("payload", {})
    decision_by = state.get("decision_by")

    outcome = mock_llm.execute_action(
        action_type=action_type,
        payload=payload,
        decision_by=decision_by,
        is_modified=is_modified,
    )

    log_entry = f"Executed action '{action_type}'. Status: {outcome['success']}. Output: {outcome['output']}"
    return {
        "status": "completed",
        "result": outcome["output"],
        "payload": payload,
        "execution_logs": [log_entry],
    }


def rejection_node(state: ApprovalAgentState) -> dict[str, Any]:
    """Bypass execution when action is rejected by human reviewer."""
    action_type = state["action_type"]
    decision_by = state.get("decision_by", "reviewer")
    reason = state.get("decision_reason", "No reason provided")
    result_msg = f"Action '{action_type}' cancelled by reviewer {decision_by}. Reason: {reason}"
    log_entry = f"Action cancelled at approval gate. Reason: {reason}"
    return {
        "status": "rejected",
        "result": result_msg,
        "execution_logs": [log_entry],
    }


def audit_node(state: ApprovalAgentState) -> dict[str, Any]:
    """Record completion timestamp and final telemetry into audit log."""
    now = datetime.now(timezone.utc).isoformat()
    status = state.get("status", "completed")
    log_entry = f"Audit finalized: lifecycle concluded with status '{status}' at {now}."
    return {
        "completed_at": now,
        "execution_logs": [log_entry],
    }


def route_after_triage(state: ApprovalAgentState) -> str:
    """Route low risk actions directly to execution; pause others at approval gate."""
    if state.get("risk_level") == "LOW":
        return "execution_node"
    return "approval_gate_node"


def route_after_gate(state: ApprovalAgentState) -> str:
    """Route to execution if approved or modified; route to rejection if rejected."""
    decision = state.get("decision", "approve")
    if decision == "reject":
        return "rejection_node"
    return "execution_node"
