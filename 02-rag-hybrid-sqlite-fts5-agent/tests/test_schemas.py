"""Tier 1: Pydantic v2 validation and schema contract tests."""

import pytest
from pydantic import ValidationError

from app.models import (
    DocumentBatchCreate,
    DocumentCreate,
    DocumentResponse,
    ErrorDetail,
    HealthResponse,
    RAGQueryRequest,
    RAGQueryResponse,
    RetrievedChunk,
)


@pytest.mark.unit
class TestDocumentSchemas:
    """Validate document creation and ingestion schemas."""

    def test_document_create_valid(self) -> None:
        doc = DocumentCreate(
            title="WAL Mode In Depth",
            content="Detailed exploration of SQLite WAL mode.",
            metadata={"source": "docs", "tier": 1},
        )
        assert doc.title == "WAL Mode In Depth"
        assert doc.content == "Detailed exploration of SQLite WAL mode."
        assert doc.metadata["tier"] == 1
        assert doc.id is None

    def test_document_create_custom_id(self) -> None:
        doc = DocumentCreate(
            id="custom_id_123",
            title="Custom ID Document",
            content="Testing custom ID support.",
        )
        assert doc.id == "custom_id_123"

    def test_document_create_empty_title_fails(self) -> None:
        with pytest.raises(ValidationError):
            DocumentCreate(title="", content="Valid content")

    def test_document_create_empty_content_fails(self) -> None:
        with pytest.raises(ValidationError):
            DocumentCreate(title="Valid title", content="")

    def test_document_create_extra_field_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            DocumentCreate(
                title="Title",
                content="Content",
                unrecognized_extra_key="forbidden",  # type: ignore
            )

    def test_document_batch_create_valid(self) -> None:
        batch = DocumentBatchCreate(
            documents=[
                DocumentCreate(title="Doc 1", content="Content 1"),
                DocumentCreate(title="Doc 2", content="Content 2"),
            ]
        )
        assert len(batch.documents) == 2

    def test_document_batch_create_empty_list_fails(self) -> None:
        with pytest.raises(ValidationError):
            DocumentBatchCreate(documents=[])

    def test_document_response_attributes(self) -> None:
        resp = DocumentResponse(
            id="doc_test_1",
            title="Response Test",
            content="Content for response",
            metadata={"author": "Team"},
            created_at="2026-11-02T00:00:00Z",
            updated_at="2026-11-02T00:00:00Z",
        )
        data = resp.model_dump()
        assert data["id"] == "doc_test_1"
        assert data["metadata"]["author"] == "Team"


@pytest.mark.unit
class TestRAGSchemas:
    """Validate RAG query requests, responses, and chunk representations."""

    def test_rag_query_request_valid(self) -> None:
        req = RAGQueryRequest(
            query="What is SQLite WAL mode?",
            top_k=3,
            threshold=0.5,
            enable_decomposition=True,
            max_iterations=2,
        )
        assert req.query == "What is SQLite WAL mode?"
        assert req.top_k == 3
        assert req.max_iterations == 2

    def test_rag_query_request_empty_query_fails(self) -> None:
        with pytest.raises(ValidationError):
            RAGQueryRequest(query="")

    def test_rag_query_request_top_k_bounds(self) -> None:
        with pytest.raises(ValidationError):
            RAGQueryRequest(query="Valid", top_k=0)
        with pytest.raises(ValidationError):
            RAGQueryRequest(query="Valid", top_k=51)

    def test_rag_query_request_max_iterations_bounds(self) -> None:
        with pytest.raises(ValidationError):
            RAGQueryRequest(query="Valid", max_iterations=0)
        with pytest.raises(ValidationError):
            RAGQueryRequest(query="Valid", max_iterations=6)

    def test_rag_query_request_extra_field_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            RAGQueryRequest(query="Valid", unexpected_param="bad")  # type: ignore

    def test_retrieved_chunk_schema(self) -> None:
        chunk = RetrievedChunk(
            id="doc_chunk_1",
            title="Chunk Title",
            content="Chunk full text",
            snippet="<b>Chunk</b> snippet",
            score=-1.25,
            metadata={"tag": "chunk"},
        )
        assert chunk.id == "doc_chunk_1"
        assert chunk.score == -1.25
        assert "<b>" in chunk.snippet

    def test_rag_query_response_schema(self) -> None:
        resp = RAGQueryResponse(
            query="Explain FTS5",
            subqueries=["Explain FTS5"],
            retrieved_docs=[
                RetrievedChunk(
                    id="doc_fts5",
                    title="FTS5 Guide",
                    content="FTS5 provides BM25 full-text indexing.",
                    snippet="<b>FTS5</b> provides...",
                    score=-0.8,
                )
            ],
            is_relevant=True,
            answer="FTS5 provides BM25 full-text indexing. [Doc: FTS5 Guide]",
            citations=["[Doc: FTS5 Guide]"],
            iterations=1,
            completed=True,
        )
        assert resp.is_relevant is True
        assert len(resp.citations) == 1
        assert resp.completed is True


@pytest.mark.unit
class TestSystemSchemas:
    """Validate healthcheck and RFC 7807 problem details schemas."""

    def test_health_response_schema(self) -> None:
        health = HealthResponse(
            status="ready",
            journal_mode="wal",
            database=":memory:",
            document_count=42,
        )
        assert health.status == "ready"
        assert health.journal_mode == "wal"
        assert health.document_count == 42
        assert health.timestamp is not None

    def test_error_detail_rfc7807_schema(self) -> None:
        error = ErrorDetail(
            title="Not Found",
            status=404,
            detail="The requested resource could not be found.",
            instance="/api/v1/documents/missing",
        )
        assert error.status == 404
        assert error.instance == "/api/v1/documents/missing"
        assert error.type == "about:blank"
