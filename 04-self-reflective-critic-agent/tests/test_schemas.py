"""Tier 1: Pydantic v2 schema and boundary validation tests."""

import pytest
from pydantic import ValidationError

from app.models import (
    ErrorDetail,
    EvaluationResult,
    LiveResponse,
    ReadyResponse,
    ReflectionExecuteRequest,
    ReflectionStep,
    RubricCriterion,
    SearchResultItem,
    SearchReflectionsResponse,
    SessionDetailResponse,
    StandaloneEvaluateRequest,
    StandaloneEvaluateResponse,
)


class TestRubricCriterionSchema:
    """Tests for RubricCriterion schema validation."""

    def test_valid_criterion(self) -> None:
        c = RubricCriterion(name="correctness", weight=1.5, description="Check edge cases")
        assert c.name == "correctness"
        assert c.weight == 1.5
        assert c.description == "Check edge cases"

    def test_default_weight(self) -> None:
        c = RubricCriterion(name="clarity")
        assert c.weight == 1.0
        assert c.description is None

    def test_weight_boundary_negative_fails(self) -> None:
        with pytest.raises(ValidationError):
            RubricCriterion(name="correctness", weight=0.0)

        with pytest.raises(ValidationError):
            RubricCriterion(name="correctness", weight=-1.0)

    def test_weight_boundary_excessive_fails(self) -> None:
        with pytest.raises(ValidationError):
            RubricCriterion(name="correctness", weight=15.0)

    def test_empty_name_fails(self) -> None:
        with pytest.raises(ValidationError):
            RubricCriterion(name="", weight=1.0)

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            RubricCriterion(name="correctness", extra_field="forbidden")  # type: ignore[call-arg]


class TestEvaluationResultSchema:
    """Tests for EvaluationResult schema validation."""

    def test_valid_evaluation_result(self) -> None:
        res = EvaluationResult(
            criteria_scores={"correctness": 88.0, "clarity": 92.0},
            composite_score=90.0,
            critique="Well structured solution.",
            defects=[],
            suggestions=["Add docstring."],
            passed=True,
        )
        assert res.composite_score == 90.0
        assert res.passed is True
        assert len(res.criteria_scores) == 2

    def test_composite_score_bounds(self) -> None:
        with pytest.raises(ValidationError):
            EvaluationResult(
                criteria_scores={},
                composite_score=-5.0,
                critique="Failed",
                passed=False,
            )

        with pytest.raises(ValidationError):
            EvaluationResult(
                criteria_scores={},
                composite_score=105.0,
                critique="Passed",
                passed=True,
            )


class TestReflectionStepSchema:
    """Tests for ReflectionStep iteration record schema."""

    def test_valid_reflection_step(self) -> None:
        step = ReflectionStep(
            iteration=1,
            draft="def foo(): pass",
            critique="Initial naive draft.",
            rubric_scores={"correctness": 60.0},
            composite_score=60.0,
            status="in_progress",
            created_at="2026-11-02T12:00:00Z",
        )
        assert step.iteration == 1
        assert step.composite_score == 60.0

    def test_invalid_iteration_index(self) -> None:
        with pytest.raises(ValidationError):
            ReflectionStep(
                iteration=0,
                draft="def foo(): pass",
                critique="Invalid",
                rubric_scores={},
                composite_score=50.0,
                status="in_progress",
                created_at="2026-11-02T12:00:00Z",
            )


class TestReflectionExecuteRequestSchema:
    """Tests for ReflectionExecuteRequest schema."""

    def test_valid_request(self) -> None:
        req = ReflectionExecuteRequest(
            task="Implement a balanced binary search tree in Python",
            threshold=85.0,
            max_iterations=4,
        )
        assert req.threshold == 85.0
        assert req.max_iterations == 4
        assert req.custom_rubric is None

    def test_task_too_short_fails(self) -> None:
        with pytest.raises(ValidationError):
            ReflectionExecuteRequest(task="hi")

    def test_task_too_long_fails(self) -> None:
        with pytest.raises(ValidationError):
            ReflectionExecuteRequest(task="A" * 2005)

    def test_threshold_out_of_bounds_fails(self) -> None:
        with pytest.raises(ValidationError):
            ReflectionExecuteRequest(task="Valid task", threshold=-1.0)
        with pytest.raises(ValidationError):
            ReflectionExecuteRequest(task="Valid task", threshold=105.0)

    def test_max_iterations_bounds(self) -> None:
        with pytest.raises(ValidationError):
            ReflectionExecuteRequest(task="Valid task", max_iterations=0)
        with pytest.raises(ValidationError):
            ReflectionExecuteRequest(task="Valid task", max_iterations=15)

    def test_with_custom_rubric(self) -> None:
        req = ReflectionExecuteRequest(
            task="Valid task prompt",
            custom_rubric=[
                RubricCriterion(name="correctness", weight=2.0),
                RubricCriterion(name="speed", weight=1.0),
            ],
        )
        assert req.custom_rubric is not None
        assert len(req.custom_rubric) == 2


class TestStandaloneEvaluateSchema:
    """Tests for StandaloneEvaluateRequest and Response schemas."""

    def test_valid_standalone_evaluate(self) -> None:
        req = StandaloneEvaluateRequest(
            task="Calculate Fibonacci numbers",
            candidate_text="def fib(n): return n if n < 2 else fib(n-1) + fib(n-2)",
            threshold=80.0,
        )
        assert req.threshold == 80.0

    def test_empty_candidate_text_fails(self) -> None:
        with pytest.raises(ValidationError):
            StandaloneEvaluateRequest(
                task="Calculate Fibonacci",
                candidate_text="",
            )

    def test_standalone_response_serialization(self) -> None:
        eval_res = EvaluationResult(
            criteria_scores={"correctness": 80.0},
            composite_score=80.0,
            critique="Passed",
            defects=[],
            suggestions=[],
            passed=True,
        )
        resp = StandaloneEvaluateResponse(
            task="Calculate Fibonacci",
            candidate_text="def fib(n): pass",
            evaluation=eval_res,
        )
        assert resp.evaluation.passed is True


class TestDiagnosticAndErrorSchemas:
    """Tests for ErrorDetail, LiveResponse, and ReadyResponse schemas."""

    def test_error_detail_rfc7807(self) -> None:
        err = ErrorDetail(
            type="https://example.com/not-found",
            title="Session Not Found",
            status=404,
            detail="Session 'sess_123' does not exist.",
            instance="/api/v1/reflections/sessions/sess_123",
        )
        assert err.status == 404
        assert "sess_123" in err.detail

    def test_health_schemas(self) -> None:
        live = LiveResponse(status="alive", service="self-reflective-critic-agent")
        assert live.status == "alive"

        ready = ReadyResponse(
            status="ready",
            database="data/test.db",
            journal_mode="wal",
            sessions_count=5,
            reflections_count=12,
        )
        assert ready.journal_mode == "wal"
        assert ready.sessions_count == 5


class TestSearchAndSessionDetailSchemas:
    """Tests for SearchResultItem and SessionDetailResponse schemas."""

    def test_search_result_item(self) -> None:
        item = SearchResultItem(
            reflection_id="refl_1",
            session_id="sess_1",
            iteration=1,
            draft="def test(): pass",
            critique="Initial code",
            rubric_scores={"correctness": 70.0},
            composite_score=70.0,
            score=-1.25,
            snippet="def <b>test</b>(): pass",
        )
        assert item.iteration == 1
        assert item.score == -1.25

    def test_search_reflections_response(self) -> None:
        resp = SearchReflectionsResponse(
            query="test",
            total_results=0,
            results=[],
        )
        assert resp.total_results == 0

    def test_session_detail_response(self) -> None:
        sess = SessionDetailResponse(
            id="sess_01",
            task="Write quicksort",
            rubric=None,
            threshold=85.0,
            status="completed",
            final_score=92.0,
            iterations=[],
            created_at="2026-11-02T12:00:00Z",
            updated_at="2026-11-02T12:05:00Z",
        )
        assert sess.final_score == 92.0
