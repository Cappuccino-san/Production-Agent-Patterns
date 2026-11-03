"""Domain models and Pydantic v2 schemas for RAG Hybrid SQLite FTS5 agent."""

from datetime import datetime, timezone
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field


class DocumentCreate(BaseModel):
    """Schema for document creation and ingestion."""

    model_config = ConfigDict(extra="forbid")

    id: Optional[str] = Field(
        default=None,
        description="Optional custom document ID; generated if omitted.",
        max_length=128,
    )
    title: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Document title for indexing and citations.",
    )
    content: str = Field(
        ...,
        min_length=1,
        description="Primary text body of the document.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary structured metadata key-value pairs.",
    )


class DocumentBatchCreate(BaseModel):
    """Schema for batch document ingestion."""

    model_config = ConfigDict(extra="forbid")

    documents: list[DocumentCreate] = Field(
        ...,
        min_length=1,
        max_length=500,
        description="List of documents to ingest concurrently.",
    )


class DocumentResponse(BaseModel):
    """Schema for document representation in responses."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class DocumentListResponse(BaseModel):
    """Paginated or listed collection of documents."""

    documents: list[DocumentResponse]
    total: int


class RetrievedChunk(BaseModel):
    """Schema for an individual search result chunk ranked by FTS5 BM25."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    content: str
    snippet: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchQueryRequest(BaseModel):
    """Direct search query request."""

    query: str = Field(..., min_length=1, max_length=2000)
    limit: int = Field(default=10, ge=1, le=100)
    threshold: float = Field(default=0.0)


class SearchQueryResponse(BaseModel):
    """Direct search query response."""

    query: str
    total_results: int
    results: list[RetrievedChunk]


class RAGQueryRequest(BaseModel):
    """Request payload for initiating LangGraph RAG reasoning workflow."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Natural language question to answer using RAG.",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Maximum documents to retrieve per subquery.",
    )
    threshold: float = Field(
        default=0.0,
        description="Minimum relevance score threshold for retrieved documents.",
    )
    enable_decomposition: bool = Field(
        default=True,
        description="Whether to decompose composite questions into subqueries.",
    )
    max_iterations: int = Field(
        default=2,
        ge=1,
        le=5,
        description="Maximum query reformulation loops on low relevance.",
    )


class RAGQueryResponse(BaseModel):
    """Synthesized RAG response with verifiable citations and audit state."""

    model_config = ConfigDict(from_attributes=True)

    query: str
    subqueries: list[str] = Field(default_factory=list)
    retrieved_docs: list[RetrievedChunk] = Field(default_factory=list)
    is_relevant: bool = True
    answer: str
    citations: list[str] = Field(default_factory=list)
    iterations: int = 1
    completed: bool = True


class HealthResponse(BaseModel):
    """Healthcheck endpoint status schema."""

    status: str
    journal_mode: str
    database: str
    document_count: Optional[int] = None
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class ErrorDetail(BaseModel):
    """RFC 7807 compliant problem details response."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str
    instance: Optional[str] = None
