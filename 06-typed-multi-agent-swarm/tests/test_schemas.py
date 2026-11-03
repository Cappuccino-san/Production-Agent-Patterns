"""Tier 1: Pydantic v2 Schema and DTO Validation Tests."""

import pytest
from pydantic import ValidationError
from app.models import (
    CodeArtifact,
    ResearchFinding,
    ReviewAssessment,
    RFC7807Error,
    SwarmStatus,
    SwarmStepLog,
    SwarmTaskRequest,
    SwarmTaskResponse,
)


class TestSchemaValidation:
    def test_research_finding_valid(self):
        finding = ResearchFinding(
            topic="Distributed Consensus",
            key_points=["Raft algorithm", "Leader election"],
            recommendations=["Use heartbeat timer"],
            confidence=0.95,
        )
        assert finding.topic == "Distributed Consensus"
        assert len(finding.key_points) == 2
        assert finding.confidence == 0.95
        assert finding.created_at is not None

    def test_research_finding_invalid_confidence_raises(self):
        with pytest.raises(ValidationError):
            ResearchFinding(
                topic="Invalid Confidence",
                key_points=["Point 1"],
                confidence=1.5,  # Exceeds le=1.0
            )

    def test_research_finding_too_short_topic_raises(self):
        with pytest.raises(ValidationError):
            ResearchFinding(
                topic="AB",  # min_length=3
                key_points=["Point 1"],
                confidence=0.5,
            )

    def test_code_artifact_valid(self):
        artifact = CodeArtifact(
            filename="solution.py",
            language="python",
            code="def add(a: int, b: int) -> int:\n    return a + b\n",
            test_cases="def test_add():\n    assert add(1, 2) == 3\n",
            dependencies=["pytest"],
        )
        assert artifact.filename == "solution.py"
        assert artifact.language == "python"
        assert "pytest" in artifact.dependencies

    def test_code_artifact_empty_code_raises(self):
        with pytest.raises(ValidationError):
            CodeArtifact(
                filename="solution.py",
                language="python",
                code="short",  # min_length=10
                test_cases="def test(): pass",
            )

    def test_review_assessment_valid(self):
        review = ReviewAssessment(
            approved=True,
            score=95.0,
            critiques=[],
            suggested_fixes=[],
        )
        assert review.approved is True
        assert review.score == 95.0

    def test_review_assessment_invalid_score_raises(self):
        with pytest.raises(ValidationError):
            ReviewAssessment(
                approved=False,
                score=105.0,  # Exceeds le=100.0
            )

    def test_swarm_task_request_defaults(self):
        req = SwarmTaskRequest(task_description="Build an async rate limiter")
        assert req.max_iterations == 3
        assert req.context is None

    def test_swarm_task_request_bounds(self):
        with pytest.raises(ValidationError):
            SwarmTaskRequest(task_description="Hi")  # min_length=5

    def test_rfc7807_error_serialization(self):
        err = RFC7807Error(
            title="Entity Not Found",
            status=404,
            detail="Item with ID 123 was not found.",
        )
        data = err.model_dump()
        assert data["status"] == 404
        assert data["title"] == "Entity Not Found"
        assert data["type"] == "about:blank"
