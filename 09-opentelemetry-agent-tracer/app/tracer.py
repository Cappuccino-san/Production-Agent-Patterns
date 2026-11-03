"""OpenTelemetry Agent Tracer engine capturing LLM hops, token metrics, tool latency, and state mutations."""

import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Generator, Optional
from app.models import AgentSpan, AgentTrace, SpanAttributes, SpanType


class AgentTracer:
    """Manages active OpenTelemetry traces and span hierarchies for autonomous agents."""

    def __init__(self) -> None:
        self.active_traces: dict[str, AgentTrace] = {}

    def start_trace(self, agent_name: str, sink: str = "LangSmith") -> str:
        trace_id = f"trc-{uuid.uuid4().hex[:12]}"
        root_span_id = f"span-{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).isoformat()

        root_span = AgentSpan(
            span_id=root_span_id,
            trace_id=trace_id,
            parent_span_id=None,
            span_type=SpanType.CHAIN_RUN,
            name=f"{agent_name}:RootChain",
            start_time=now,
            end_time=now,
            duration_ms=0.0,
            attributes=SpanAttributes(extra_metadata={"agent_name": agent_name}),
        )

        trace = AgentTrace(
            trace_id=trace_id,
            agent_name=agent_name,
            root_span_id=root_span_id,
            total_tokens=0,
            total_duration_ms=0.0,
            sink=sink,
            created_at=now,
            spans=[root_span],
        )
        self.active_traces[trace_id] = trace
        return trace_id

    def record_llm_hop(
        self,
        trace_id: str,
        model_name: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: float,
        step_name: str = "LLMInference",
    ) -> AgentSpan:
        trace = self.active_traces.get(trace_id)
        span_id = f"span-llm-{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).isoformat()
        total_tokens = prompt_tokens + completion_tokens

        attrs = SpanAttributes(
            model_name=model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
        )

        span = AgentSpan(
            span_id=span_id,
            trace_id=trace_id,
            parent_span_id=trace.root_span_id if trace else None,
            span_type=SpanType.LLM_HOP,
            name=step_name,
            start_time=now,
            end_time=now,
            duration_ms=latency_ms,
            attributes=attrs,
        )

        if trace:
            trace.spans.append(span)
            trace.total_tokens += total_tokens
            trace.total_duration_ms += latency_ms

        return span

    def record_tool_execution(
        self,
        trace_id: str,
        tool_name: str,
        latency_ms: float,
        status_code: int = 200,
        extra: Optional[dict[str, Any]] = None,
    ) -> AgentSpan:
        trace = self.active_traces.get(trace_id)
        span_id = f"span-tool-{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).isoformat()

        attrs = SpanAttributes(
            tool_name=tool_name,
            latency_ms=latency_ms,
            status_code=status_code,
            extra_metadata=extra or {},
        )

        span = AgentSpan(
            span_id=span_id,
            trace_id=trace_id,
            parent_span_id=trace.root_span_id if trace else None,
            span_type=SpanType.TOOL_LATENCY,
            name=f"Tool:{tool_name}",
            start_time=now,
            end_time=now,
            duration_ms=latency_ms,
            attributes=attrs,
        )

        if trace:
            trace.spans.append(span)
            trace.total_duration_ms += latency_ms

        return span

    def record_state_mutation(
        self,
        trace_id: str,
        variable_name: str,
        old_value: Any,
        new_value: Any,
    ) -> AgentSpan:
        trace = self.active_traces.get(trace_id)
        span_id = f"span-mut-{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).isoformat()

        attrs = SpanAttributes(
            state_delta={
                "variable": variable_name,
                "old": old_value,
                "new": new_value,
            }
        )

        span = AgentSpan(
            span_id=span_id,
            trace_id=trace_id,
            parent_span_id=trace.root_span_id if trace else None,
            span_type=SpanType.STATE_MUTATION,
            name=f"Mutation:{variable_name}",
            start_time=now,
            end_time=now,
            duration_ms=0.1,
            attributes=attrs,
        )

        if trace:
            trace.spans.append(span)

        return span

    def export_trace(self, trace_id: str) -> Optional[AgentTrace]:
        return self.active_traces.get(trace_id)
