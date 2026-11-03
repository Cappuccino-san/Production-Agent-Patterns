"""Tier 2: LangGraph State Machine Traced Span Capture Tests."""

import pytest
from app.agent.graph import create_traced_graph
from app.models import SpanType
from app.tracer import AgentTracer


class TestAgentGraph:
    def test_traced_graph_execution_captures_all_spans(self, temp_db: str, test_tracer: AgentTracer):
        graph = create_traced_graph(temp_db, test_tracer)
        trace_id = test_tracer.start_trace(agent_name="TestOrchestrator", sink="Arize")

        initial_state = {
            "trace_id": trace_id,
            "task_prompt": "Inspect database performance and optimize indexes",
            "intermediate_thought": "",
            "tool_output": "",
            "final_output": "",
            "total_tokens": 0,
            "spans": [],
        }

        result = graph.invoke(initial_state)

        assert "Agent task execution completed" in result["final_output"]
        assert result["total_tokens"] > 0

        # Verify emitted spans
        exported = test_tracer.export_trace(trace_id)
        assert exported is not None
        assert exported.sink == "Arize"

        span_types = [s.span_type for s in exported.spans]
        assert SpanType.CHAIN_RUN in span_types
        assert SpanType.LLM_HOP in span_types
        assert SpanType.TOOL_LATENCY in span_types
        assert SpanType.STATE_MUTATION in span_types

        # Verify LLM Hop token attributes
        llm_span = next(s for s in exported.spans if s.span_type == SpanType.LLM_HOP)
        assert llm_span.attributes.prompt_tokens == 142
        assert llm_span.attributes.completion_tokens == 68
        assert llm_span.attributes.total_tokens == 210

        # Verify Tool Latency attributes
        tool_span = next(s for s in exported.spans if s.span_type == SpanType.TOOL_LATENCY)
        assert tool_span.attributes.tool_name == "sqlite_introspection"
        assert tool_span.attributes.latency_ms > 0.0

        # Verify State Mutation attributes
        mut_span = next(s for s in exported.spans if s.span_type == SpanType.STATE_MUTATION)
        assert mut_span.attributes.state_delta["variable"] == "final_output"
