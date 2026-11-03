"""Implementation of production and candidate agent topologies."""

import time
from app.models import ToolCallRecord, TrajectorySummary


def execute_primary_topology(prompt: str) -> TrajectorySummary:
    """Executes standard production ReAct topology (sequential tool execution)."""
    t0 = time.time()
    tools = [
        ToolCallRecord(
            step_index=1,
            tool_name="web_search",
            input_arguments={"query": prompt[:80]},
            latency_ms=42.0,
            status="SUCCESS",
        ),
        ToolCallRecord(
            step_index=2,
            tool_name="eval_metric",
            input_arguments={"context": "search_results_v1"},
            latency_ms=28.0,
            status="SUCCESS",
        ),
    ]
    elapsed_ms = (time.time() - t0) * 1000.0 + 70.0  # simulated network hop

    return TrajectorySummary(
        topology_name="STANDARD_REACT",
        tool_calls=tools,
        total_tokens=650,
        cost_usd=0.0095,
        latency_ms=round(elapsed_ms, 2),
        final_output=f"Standard ReAct synthesis completed for: {prompt[:60]}",
    )


def execute_candidate_topology(prompt: str) -> TrajectorySummary:
    """Executes experimental candidate topology (Parallel Speculative ReAct)."""
    t0 = time.time()
    tools = [
        ToolCallRecord(
            step_index=1,
            tool_name="speculative_query_optimizer",
            input_arguments={"prompt": prompt[:80]},
            latency_ms=18.0,
            status="SUCCESS",
        ),
        ToolCallRecord(
            step_index=2,
            tool_name="batched_retrieval",
            input_arguments={"batch_size": 3},
            latency_ms=22.0,
            status="SUCCESS",
        ),
        ToolCallRecord(
            step_index=3,
            tool_name="cross_encoder_rerank",
            input_arguments={"top_k": 3},
            latency_ms=12.0,
            status="SUCCESS",
        ),
    ]
    elapsed_ms = (time.time() - t0) * 1000.0 + 45.0  # optimized parallel hop

    return TrajectorySummary(
        topology_name="PARALLEL_SPECULATIVE_REACT",
        tool_calls=tools,
        total_tokens=420,
        cost_usd=0.0042,
        latency_ms=round(elapsed_ms, 2),
        final_output=f"Candidate speculative synthesis completed with optimized token density for: {prompt[:60]}",
    )
