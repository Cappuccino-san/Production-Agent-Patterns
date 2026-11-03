"""Tier 1: Pydantic Schema Validation Tests for OpenTelemetry Tracing."""

import pytest
from pydantic import ValidationError
from app.models import (
    AgentSpan,
    AgentTrace,
    RFC7807Error,
    SpanAttributes,
    SpanType,
    TraceRunRequest,
)


class TestSchemas:
    def test_span_attributes_valid(self):
        attrs = SpanAttributes(
            model_name="claude-3-5-sonnet",
            prompt_tokens=150,
            completion_tokens=50,
            total_tokens=200,
            latency_ms=180.5,
            tool_name=None,
        )
        assert attrs.total_tokens == 200
        assert attrs.latency_ms == 180.5

    def test_agent_span_model(self):
        span = AgentSpan(
            span_id="span-1",
            trace_id="trc-1",
            parent_span_id="root-1",
            span_type=SpanType.LLM_HOP,
            name="LLMInference",
            start_time="2026-11-02T12:00:00Z",
            end_time="2026-11-02T12:00:01Z",
            duration_ms=1000.0,
            attributes=SpanAttributes(prompt_tokens=10, completion_tokens=10, total_tokens=20),
        )
        assert span.span_type == SpanType.LLM_HOP
        assert span.duration_ms == 1000.0

    def test_trace_run_request_valid(self):
        req = TraceRunRequest(
            agent_name="CoderAgent",
            prompt="Refactor database layer to support WAL mode",
            destination_sink="LangSmith",
        )
        assert req.destination_sink == "LangSmith"

    def test_trace_run_request_invalid_sink_raises(self):
        with pytest.raises(ValidationError):
            TraceRunRequest(
                agent_name="CoderAgent",
                prompt="Valid prompt",
                destination_sink="InvalidSink",
            )

    def test_rfc7807_error_model(self):
        err = RFC7807Error(
            title="Trace Not Found",
            status=404,
            detail="The requested trace id does not exist",
        )
        assert err.status == 404
