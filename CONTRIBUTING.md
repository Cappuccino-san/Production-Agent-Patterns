# Contributing to Production Agent Patterns (PAP-15)

Thank you for your interest in contributing to the **Production Agent Patterns** repository! We welcome contributions to our 15 reference architectures.

---

## Architecture Standards

All contributions, extensions, or new tools must adhere to our universal enterprise requirements:

1. **Python & Frameworks**:
   - Python 3.11+
   - FastAPI with asynchronous endpoints (`async def`)
   - Pydantic v2 schemas for all inputs, outputs, and state models
   - LangGraph `StateGraph` with explicit state definitions and cycle limits
2. **State Management**:
   - Native SQLite configured in WAL mode:
     `PRAGMA journal_mode = WAL; PRAGMA synchronous = NORMAL; PRAGMA foreign_keys = ON; PRAGMA busy_timeout = 5000;`
   - External content FTS5 virtual tables with automated triggers (`AFTER INSERT`, `AFTER DELETE`, `AFTER UPDATE`)
3. **Containerization**:
   - Multi-stage Dockerfile (`python:3.11-slim`) with non-root security context (`USER appuser`)
   - Standardized `docker-compose.yml`
4. **Testing Rigor**:
   - 5-tier test pyramid in `tests/`: `test_schemas.py`, `test_agent_graph.py`, `test_persistence.py`, `test_api_contracts.py`, `test_boundary_resilience.py`
   - All tests must pass with zero mock leaks or external API dependencies

---

## Submitting Pull Requests

1. **Fork and Branch**: Create a feature branch off `main` (`feature/my-enhancement`).
2. **Run Pytest Validation**:
   ```bash
   pytest <repo-directory>/tests -v
   ```
3. **Commit Guidelines**: Use Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`).
4. **Open a PR**: Fill out the PR summary detailing the architecture pattern and test results.
