"""Node implementations for Cost Kill-Switch and Fallback Middleware."""

import uuid
from datetime import datetime, timezone
from app.agent.state import CostAgentState
from app.models import CostLedgerEntry, CostStatus
from app.pricing import calculate_step_cost, evaluate_cost_kill_switch


def frontier_planner_node(state: CostAgentState) -> dict:
    """Executes high-capability frontier model step (gpt-4o) with strict cost monitoring."""
    step_num = state.current_step + 1
    model = "gpt-4o"

    if state.force_spend_spike:
        # Simulate extreme output tokens that breach $0.50 budget
        p_tokens = 8_000
        c_tokens = 32_000
    else:
        p_tokens = 350
        c_tokens = 200

    step_cost = calculate_step_cost(model, p_tokens, c_tokens)
    projected_total = state.current_spend_usd + step_cost

    triggered, fallback, reason = evaluate_cost_kill_switch(
        current_spend_usd=state.current_spend_usd,
        projected_step_cost_usd=step_cost,
        current_depth=step_num,
        max_spend_usd=0.50,
        max_depth=5,
    )

    ledger_entry = CostLedgerEntry(
        ledger_id=str(uuid.uuid4()),
        request_id=state.request_id,
        step_index=step_num,
        model_used=model,
        prompt_tokens=p_tokens,
        completion_tokens=c_tokens,
        step_cost_usd=step_cost,
        cumulative_cost_usd=round(projected_total, 6),
        loop_depth=step_num,
        kill_switch_active=triggered,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    new_ledger = list(state.ledger)
    new_ledger.append(ledger_entry)

    if triggered:
        return {
            "current_step": step_num,
            "current_spend_usd": round(projected_total, 6),
            "total_tokens": state.total_tokens + p_tokens + c_tokens,
            "kill_switch_triggered": True,
            "ledger": new_ledger,
            "final_output": f"Kill switch triggered: {reason}",
        }

    # Normal completion check
    is_last = step_num >= state.max_iterations
    status = CostStatus.COMPLETED if is_last else CostStatus.ACTIVE
    output = f"Completed synthesis with {model} at step {step_num}: {state.prompt[:80]}" if is_last else ""

    return {
        "current_step": step_num,
        "current_model": model,
        "current_spend_usd": round(projected_total, 6),
        "total_tokens": state.total_tokens + p_tokens + c_tokens,
        "status": status,
        "ledger": new_ledger,
        "final_output": output,
    }


def fallback_router_node(state: CostAgentState) -> dict:
    """Evaluates whether to fallback to cheaper gpt-4o-mini or halt completely."""
    # If spend already exceeded $0.55 or user explicitly breached hard ceiling, halt
    if state.current_spend_usd > 0.60:
        return {
            "status": CostStatus.HALTED_BUDGET_EXCEEDED,
            "final_output": f"Circuit breaker tripped: Total spend ${state.current_spend_usd:.4f} exceeds absolute budget ceiling. Execution halted.",
        }

    return {
        "current_model": "gpt-4o-mini",
        "fallback_engaged": True,
        "status": CostStatus.FALLBACK_ENGAGED,
    }


def fallback_worker_node(state: CostAgentState) -> dict:
    """Executes subsequent steps on budget-friendly gpt-4o-mini."""
    step_num = state.current_step + 1
    model = "gpt-4o-mini"
    p_tokens = 300
    c_tokens = 150
    step_cost = calculate_step_cost(model, p_tokens, c_tokens)
    new_total = round(state.current_spend_usd + step_cost, 6)

    ledger_entry = CostLedgerEntry(
        ledger_id=str(uuid.uuid4()),
        request_id=state.request_id,
        step_index=step_num,
        model_used=model,
        prompt_tokens=p_tokens,
        completion_tokens=c_tokens,
        step_cost_usd=step_cost,
        cumulative_cost_usd=new_total,
        loop_depth=step_num,
        kill_switch_active=True,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    new_ledger = list(state.ledger)
    new_ledger.append(ledger_entry)

    return {
        "current_step": step_num,
        "current_model": model,
        "current_spend_usd": new_total,
        "total_tokens": state.total_tokens + p_tokens + c_tokens,
        "status": CostStatus.COMPLETED,
        "ledger": new_ledger,
        "final_output": f"Fallback execution completed using {model} within safe budget bounds. Result for '{state.prompt[:60]}'",
    }


def halt_worker_node(state: CostAgentState) -> dict:
    """Finalizes halted state when budget ceiling is rigidly enforced."""
    return {
        "status": CostStatus.HALTED_BUDGET_EXCEEDED,
        "kill_switch_triggered": True,
        "final_output": f"Execution safely halted by Cost Kill-Switch Middleware at loop depth {state.current_step}. Total spend: ${state.current_spend_usd:.4f}.",
    }
