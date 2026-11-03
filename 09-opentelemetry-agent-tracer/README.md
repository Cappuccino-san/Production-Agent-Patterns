# OpenTelemetry Agent Tracer

A production-grade distributed telemetry and tracing engine for autonomous AI agents that captures custom OpenTelemetry-compliant spans across every **LLM hop** (prompt/completion tokens, latency), **tool execution** (latency, status codes, arguments), and **state mutation** for seamless export to observability platforms like **LangSmith** and **Arize**.

---

## 1. Architectural Overview

Debugging complex agentic loops requires full visibility into token expenditures, model latencies, tool failures, and state drift. This service instruments agent executions with granular span telemetry:
- **LLM Hop Spans**: Captures model name, prompt tokens, completion tokens, total tokens, and millisecond inference latency.
- **Tool Execution Spans**: Captures tool identifiers, invocation arguments, network/process duration, and HTTP/process exit status codes.
- **State Mutation Spans**: Records state deltas (variable, pre-mutation value, post-mutation value).
- **Enterprise SQLite WAL & FTS5**: All traces and spans are persisted with zero read/write contention under WAL mode and indexed for BM25 retrieval.

```mermaid
flowchart TD
    TaskReq[TraceRunRequest] --> TracerEngine[Agent Tracer Engine]
    
    subgraph Trace_Waterfall ["OpenTelemetry Span Hierarchy"]
        TracerEngine --> RootSpan["Root Span: ChainRun"]
        RootSpan --> LLM город["LLM Hop Span (Tokens & Latency)"]
        RootSpan --> Tool город["Tool Execution Span (Duration & Status)"]
        RootSpan --> Mutation город["State Mutation Span (State Delta)"]
    end

    subgraph Observability_Sinks ["Telemetry Ingestion"]
        Trace_Waterfall --> SinkSelect{"Target Observability Sink"}
        SinkSelect -->|LangSmith| LS[(LangSmith Exporter)]
        SinkSelect -->|Arize| AZ[(Arize Phoenix Exporter)]
        SinkSelect -->|OTLP| OT[(OTLP Collector)]
    end

    subgraph Storage_Layer ["SQLite WAL & FTS5"]
        RootSpan -.-> TracesTable[(agent_traces)]
        LLM город -.-> SpansTable[(agent_spans)]
        Tool город -.-> SpansTable
        Mutation город -.-> SpansTable
        SpansTable ===>|Automated Triggers| FTS5[(agent_spans_fts BM25)]
    end
```

---

## 2. Span Hierarchy Specifications

```json
{
  "span_id": "span-llm-1a2b3c4d",
  "trace_id": "trc-010203040506",
  "parent_span_id": "span-root-9876",
  "span_type": "LLM_HOP",
  "name": "AgentReasoning",
  "duration_ms": 230.5,
  "attributes": {
    "model_name": "claude-3-5-sonnet",
    "prompt_tokens": 142,
    "completion_tokens": 68,
    "total_tokens": 210,
    "latency_ms": 230.5
  }
}
```

---

## 3. SQLite WAL Mode and FTS5 Sync

```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;

CREATE TRIGGER agent_spans_ai AFTER INSERT ON agent_spans BEGIN
    INSERT INTO agent_spans_fts(rowid, span_id, trace_id, parent_span_id, span_type, name, attributes_json)
    VALUES (new.rowid, new.span_id, new.trace_id, new.parent_span_id, new.span_type, new.name, new.attributes_json);
END;
```

---

## 4. REST API Contract

| Method | Path | Description |
|---|---|---|
| `POST` | `/traces/run-agent` | Executes agent task with full OpenTelemetry span capture |
| `GET` | `/traces/{trace_id}` | Retrieves complete trace waterfall and token metrics |
| `GET` | `/traces/search?q={query}` | BM25 search across span attributes via SQLite FTS5 |
| `GET` | `/health/live` | Process liveness check |
| `GET` | `/health/ready` | SQLite readiness check |

---

## 5. Local Setup & Testing

### Installation
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Running Test Suite
```bash
python -m pytest tests/ -v
```

---

## 6. Docker & AWS EC2 Deployment

```bash
docker-compose up -d --build
```
