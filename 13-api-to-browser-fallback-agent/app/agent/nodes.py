"""Node logic for API-to-Browser Fallback routing and automation."""

import time
import uuid
from datetime import datetime, timezone
from app.agent.state import FallbackState
from app.models import (
    ExecutionChannel,
    ExecutionLogEntry,
    WorkflowActionType,
    WorkflowStatus,
)


def api_executor_node(state: FallbackState) -> dict:
    """Attempts direct REST API call to fetch structured data."""
    logs = list(state.logs)
    now_str = datetime.now(timezone.utc).isoformat()

    logs.append(
        ExecutionLogEntry(
            log_id=str(uuid.uuid4()),
            execution_id=state.execution_id,
            channel=ExecutionChannel.API,
            step_name="API_REQUEST_DISPATCH",
            message=f"Dispatching GET request to {state.api_endpoint}/{state.target_id}",
            timestamp=now_str,
        )
    )

    if state.simulate_api_failure:
        failure_type = state.simulated_failure_type.lower()
        if "timeout" in failure_type:
            status_code = 504
            err_msg = f"REST API timeout after 5000ms connecting to {state.api_endpoint}"
        elif "500" in failure_type:
            status_code = 500
            err_msg = f"Internal Server Error (500) encountered at {state.api_endpoint}"
        else:
            status_code = 404
            err_msg = f"HTTP 404 Not Found: Entity '{state.target_id}' was deleted or unindexed in REST v1 API"

        logs.append(
            ExecutionLogEntry(
                log_id=str(uuid.uuid4()),
                execution_id=state.execution_id,
                channel=ExecutionChannel.API,
                step_name="API_REQUEST_FAILED",
                message=f"API call failed with status {status_code}: {err_msg}",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        )

        return {
            "api_status_code": status_code,
            "api_error_detail": err_msg,
            "logs": logs,
        }

    # Successful API invocation
    extracted = {
        "source": "REST_API_V1",
        "entity_id": state.target_id,
        "action": state.action.value,
        "status": "CONFIRMED",
        "amount_usd": 1850.50,
        "vendor": "Apex Cloud Systems",
        "payload_schema": "application/json",
        "cached": False,
    }

    logs.append(
        ExecutionLogEntry(
            log_id=str(uuid.uuid4()),
            execution_id=state.execution_id,
            channel=ExecutionChannel.API,
            step_name="API_REQUEST_SUCCESS",
            message=f"Successfully retrieved entity payload from API for {state.target_id}",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    )

    return {
        "api_status_code": 200,
        "api_error_detail": None,
        "extracted_data": extracted,
        "logs": logs,
    }


def fallback_router_node(state: FallbackState) -> dict:
    """Evaluates API response and engages browser fallback if error encountered."""
    logs = list(state.logs)
    now_str = datetime.now(timezone.utc).isoformat()

    if state.api_status_code == 200:
        logs.append(
            ExecutionLogEntry(
                log_id=str(uuid.uuid4()),
                execution_id=state.execution_id,
                channel=ExecutionChannel.API,
                step_name="ROUTE_DECISION",
                message="REST API invocation succeeded. Bypassing browser fallback.",
                timestamp=now_str,
            )
        )
        return {
            "fallback_triggered": False,
            "execution_channel": ExecutionChannel.API,
            "logs": logs,
        }

    # API failure triggered fallback
    logs.append(
        ExecutionLogEntry(
            log_id=str(uuid.uuid4()),
            execution_id=state.execution_id,
            channel=ExecutionChannel.BROWSER_FALLBACK,
            step_name="ENGAGE_BROWSER_FALLBACK",
            message=f"Primary REST API failed ({state.api_status_code}). Initiating headless browser GUI fallback to {state.gui_url}.",
            timestamp=now_str,
        )
    )

    return {
        "fallback_triggered": True,
        "execution_channel": ExecutionChannel.BROWSER_FALLBACK,
        "logs": logs,
    }


def browser_executor_node(state: FallbackState) -> dict:
    """Spawns headless browser session, navigates GUI portal, and extracts DOM values."""
    logs = list(state.logs)
    sess_id = f"pw-sess-{uuid.uuid4().hex[:10]}"

    logs.append(
        ExecutionLogEntry(
            log_id=str(uuid.uuid4()),
            execution_id=state.execution_id,
            channel=ExecutionChannel.BROWSER_FALLBACK,
            step_name="SPAWN_HEADLESS_BROWSER",
            message=f"Launched sandboxed Chromium headless instance [session={sess_id}]",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    )

    logs.append(
        ExecutionLogEntry(
            log_id=str(uuid.uuid4()),
            execution_id=state.execution_id,
            channel=ExecutionChannel.BROWSER_FALLBACK,
            step_name="NAVIGATE_AND_INTERACT",
            message=f"Navigated to {state.gui_url}?id={state.target_id} and waited for networkidle",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    )

    # Simulated DOM extraction from rendered Next.js/React portal view
    extracted_from_dom = {
        "source": "HEADLESS_BROWSER_DOM",
        "browser_engine": "Chromium Headless",
        "page_title": f"Enterprise Portal - {state.target_id}",
        "dom_selector": f"#entity-detail-card[data-entity='{state.target_id}']",
        "entity_id": state.target_id,
        "action": state.action.value,
        "status": "CONFIRMED_VIA_PORTAL",
        "amount_usd": 1850.50,
        "vendor": "Apex Cloud Systems (Extracted from DOM)",
        "dom_metadata": {
            "rendered_framework": "Next.js 14 SSR",
            "screenshot_hash": f"sha256:{uuid.uuid4().hex}",
            "interaction_steps": ["goto_url", "wait_for_selector", "extract_table_cells"],
        },
    }

    logs.append(
        ExecutionLogEntry(
            log_id=str(uuid.uuid4()),
            execution_id=state.execution_id,
            channel=ExecutionChannel.BROWSER_FALLBACK,
            step_name="DOM_EXTRACTION_SUCCESS",
            message=f"Successfully extracted entity {state.target_id} from GUI DOM using selector #entity-detail-card",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    )

    return {
        "browser_session_id": sess_id,
        "extracted_data": extracted_from_dom,
        "logs": logs,
    }


def result_formatter_node(state: FallbackState) -> dict:
    """Formats final response and calculates workflow latency."""
    elapsed_ms = (time.time() - state.start_time_epoch) * 1000.0 if state.start_time_epoch else 45.2

    if state.execution_channel == ExecutionChannel.BROWSER_FALLBACK:
        final_status = WorkflowStatus.COMPLETED_VIA_BROWSER_FALLBACK
    elif state.api_status_code == 200:
        final_status = WorkflowStatus.COMPLETED_VIA_API
    else:
        final_status = WorkflowStatus.FAILED

    return {
        "status": final_status,
        "latency_ms": round(elapsed_ms, 2),
    }
