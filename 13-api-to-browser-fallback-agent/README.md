# 13-api-to-browser-fallback-agent

> Autonomous routing layer that seamlessly spawns a headless browser session to complete GUI workflows whenever primary REST APIs encounter 404s, timeouts, or service interruptions.

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-teal.svg)](https://fastapi.tiangolo.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2%2B-orange.svg)](https://langchain-ai.github.io/langgraph/)
[![SQLite WAL](https://img.shields.io/badge/SQLite-WAL%20%2B%20FTS5-green.svg)](https://sqlite.org)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg)](https://www.docker.com/)

---

## 1. Architectural Overview

Production agent systems often depend on internal REST APIs that can fail due to stale route documentation, unindexed records, gateway timeouts, or deployment drift. The **API-to-Browser Fallback Agent** implements an automated resilience layer:
1. It attempts fast, structured data extraction via the primary REST API.
2. If the API returns a `404 Not Found`, `504 Gateway Timeout`, or `500 Internal Error`, a LangGraph conditional edge intercepts the failure.
3. The agent spawns a sandboxed headless browser session, navigates directly to the web portal GUI, locates the corresponding DOM selectors, extracts the structured entity, and logs the entire fallback path in SQLite WAL.

```mermaid
flowchart TD
    User([Client / API Request]) -->|POST /fallback/execute| API[FastAPI Gateway]
    API --> InitState[Initialize FallbackState]
    InitState --> APIExecutor[API Executor Node]
    
    APIExecutor -->|Dispatch REST Call| REST[Primary REST API Endpoint]
    REST --> CheckStatus{Status 200 OK?}
    
    CheckStatus -- Yes --> RouteDirect[Route Decision: API Success]
    RouteDirect --> ResultFormatter[Result Formatter Node]
    ResultFormatter --> StatusAPI[Status: COMPLETED_VIA_API]
    
    CheckStatus -- 404 / 504 / 500 --> FallbackRouter[Fallback Router Node]
    FallbackRouter --> EngageFallback[Trigger Headless Browser Fallback]
    
    EngageFallback --> BrowserExecutor[Browser Executor Node]
    BrowserExecutor --> SpawnChromium[Spawn Sandboxed Chromium Instance]
    SpawnChromium --> NavigateGUI[Navigate to Portal GUI URL]
    NavigateGUI --> ExtractDOM[Locate & Extract DOM Elements]
    ExtractDOM --> ResultFormatter
    ResultFormatter --> StatusBrowser[Status: COMPLETED_VIA_BROWSER_FALLBACK]
    
    StatusAPI --> Persist[(SQLite WAL: fallback_executions + FTS5)]
    StatusBrowser --> Persist
    Persist --> Response([JSON Response + Audit Log Trail])
```

---

## 2. Core Capabilities

- **Zero-Drop Workflow Completion**: Workflows never fail because of an unindexed API record; the GUI portal is automatically leveraged as a high-fidelity fallback.
- **Automated DOM Scraping & Extraction**: Extracts structured fields from rendered React/Next.js portal views.
- **Immutable Audit Trail in SQLite WAL**: Every dispatch hop, HTTP status code, browser session ID, DOM selector, and timing metric is logged with FTS5 search.
- **RFC 7807 Error Standard**: Problem Details returned for all validation and missing record lookups.

---

## 3. Technology Stack

- **Backend & Orchestration**: Python 3.11+, FastAPI (with asyncio), Pydantic v2, LangGraph.
- **State Management**: Native SQLite with Write-Ahead Logging (`WAL`), `synchronous = NORMAL`, `foreign_keys = ON`, `busy_timeout = 5000`, and Porter-stemmed FTS5 virtual tables with automated triggers.
- **Containerization**: Multi-stage Docker container configured for AWS EC2 and WSL2 Ubuntu deployment.

---

## 4. Quickstart

### Local Setup
```bash
# Clone and navigate
cd 13-api-to-browser-fallback-agent

# Virtual environment setup
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run pytest validation
pytest
```

### Docker Deployment
```bash
docker compose up --build
```

---

## 5. API Reference

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Service health status |
| `POST` | `/fallback/execute` | Execute workflow with automatic API-to-browser fallback |
| `GET` | `/fallback/search?q={term}` | BM25 full-text search across past execution logs |
| `GET` | `/fallback/{execution_id}` | Retrieve single execution record and sequential audit log trail |
