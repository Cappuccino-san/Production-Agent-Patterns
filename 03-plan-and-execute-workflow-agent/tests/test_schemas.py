"""Tier 1: Pydantic v2 schema validation and boundary constraint tests."""

import pytest
from pydantic import ValidationError

from app.models import (
    ErrorDetail,
    HealthResponse,
    PlanCreate,
    PlanExecuteRequest,
    PlanExecuteResponse,
    PlanResponse,
    PlanSearchResult,
    PlanStep,
    StepExecutionResult,
)


@pytest.mark.unit
class TestPlanCreateSchema:
    """Validation tests for PlanCreate request payload."""

    def test_plan_create_valid(self) -> None:
        payload = PlanCreate(goal="Implement end-to-end data pipeline with SQLite WAL")
        assert payload.goal == "Implement end-to-end data pipeline with SQLite WAL"
        assert payload.context is None

    def test_plan_create_with_context(self) -> None:
        payload = PlanCreate(
            goal="Analyze quarterly sales report",
            context={"quarter": "Q3", "region": "North America"},
        )
        assert payload.context == {"quarter": "Q3", "region": "North America"}

    def test_plan_create_empty_goal_fails(self) -> None:
        with pytest.raises(ValidationError):
            PlanCreate(goal="")

    def test_plan_create_whitespace_only_goal_fails(self) -> None:
        with pytest.raises(ValidationError):
            PlanCreate(goal="   \t\n   ")

    def test_plan_create_too_short_fails(self) -> None:
        with pytest.raises(ValidationError):
            PlanCreate(goal="ab")

    def test_plan_create_too_long_fails(self) -> None:
        with pytest.raises(ValidationError):
            PlanCreate(goal="x" * 1001)

    def test_plan_create_extra_field_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            PlanCreate.model_validate({"goal": "Valid Goal Here", "unknown_field": "disallowed"})


@pytest.mark.unit
class TestPlanStepSchema:
    """Validation tests for PlanStep domain model."""

    def test_plan_step_valid(self) -> None:
        step = PlanStep(
            id="step_123",
            plan_id="plan_abc",
            step_index=0,
            title="Setup database",
            description="Initialize SQLite tables",
            tool="database",
        )
        assert step.status == "pending"
        assert step.tool == "database"
        assert step.result is None
        assert step.error is None

    def test_plan_step_negative_index_fails(self) -> None:
        with pytest.raises(ValidationError):
            PlanStep(
                id="step_123",
                plan_id="plan_abc",
                step_index=-1,
                title="Setup database",
                description="Initialize SQLite tables",
            )

    def test_plan_step_empty_title_fails(self) -> None:
        with pytest.raises(ValidationError):
            PlanStep(
                id="step_123",
                plan_id="plan_abc",
                step_index=0,
                title="",
                description="Initialize SQLite tables",
            )

    def test_plan_step_extra_field_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            PlanStep.model_validate({
                "id": "step_1",
                "plan_id": "plan_1",
                "step_index": 0,
                "title": "Title",
                "description": "Desc",
                "bogus": "value",
            })


@pytest.mark.unit
class TestPlanResponseSchema:
    """Validation tests for PlanResponse schema."""

    def test_plan_response_valid(self) -> None:
        res = PlanResponse(
            id="plan_01",
            goal="Deploy microservice",
            status="created",
            total_steps=1,
            current_step_index=0,
            steps=[
                PlanStep(
                    id="step_01",
                    plan_id="plan_01",
                    step_index=0,
                    title="Build Dockerfile",
                    description="Multi-stage container build",
                )
            ],
            created_at="2026-11-02T00:00:00Z",
            updated_at="2026-11-02T00:00:00Z",
        )
        assert res.id == "plan_01"
        assert len(res.steps) == 1
        assert res.steps[0].title == "Build Dockerfile"


@pytest.mark.unit
class TestPlanExecuteSchemas:
    """Validation tests for PlanExecuteRequest and PlanExecuteResponse."""

    def test_plan_execute_request_defaults(self) -> None:
        req = PlanExecuteRequest()
        assert req.plan_id is None
        assert req.max_iterations is None
        assert req.allow_replanning is True

    def test_plan_execute_request_bounds(self) -> None:
        with pytest.raises(ValidationError):
            PlanExecuteRequest(max_iterations=0)
        with pytest.raises(ValidationError):
            PlanExecuteRequest(max_iterations=51)

    def test_plan_execute_response_valid(self) -> None:
        res = PlanExecuteResponse(
            plan_id="plan_xyz",
            goal="Analyze telemetry",
            status="completed",
            completed=True,
            iterations=4,
            steps=[],
            response="Synthesized output",
        )
        assert res.completed is True
        assert res.iterations == 4


@pytest.mark.unit
class TestSystemSchemas:
    """Validation tests for HealthResponse and ErrorDetail."""

    def test_health_response_schema(self) -> None:
        health = HealthResponse(
            status="healthy",
            version="0.1.0",
            database="connected",
            environment="test",
        )
        assert health.status == "healthy"
        assert health.database == "connected"

    def test_error_detail_rfc7807(self) -> None:
        err = ErrorDetail(
            title="Not Found",
            status=404,
            detail="The requested resource was not found",
            instance="/api/v1/plans/123",
        )
        assert err.type == "about:blank"
        assert err.status == 404
        assert err.instance == "/api/v1/plans/123"

    def test_step_execution_result_schema(self) -> None:
        res = StepExecutionResult(
            step_index=0,
            title="Step 1",
            tool="code",
            status="completed",
            result="Success",
        )
        assert res.status == "completed"

    def test_plan_search_result_schema(self) -> None:
        sr = PlanSearchResult(
            plan_id="plan_1",
            step_id="step_1",
            step_index=0,
            title="Search step",
            description="FTS5 query",
            result="Results found",
            score=-1.25,
            snippet="<b>FTS5</b> query",
        )
        assert sr.score == -1.25
        assert "<b>FTS5</b>" in sr.snippet
