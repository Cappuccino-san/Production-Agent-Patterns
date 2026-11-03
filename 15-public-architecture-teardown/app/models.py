"""Pydantic v2 domain schemas for Public Architecture Teardown."""

from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel, Field


class TeardownDeepDive(BaseModel):
    slug: str = Field(..., min_length=2, max_length=100)
    title: str = Field(..., min_length=5, max_length=250)
    category: str = Field(..., min_length=2, max_length=100)
    summary: str = Field(..., min_length=10, max_length=1000)
    content_markdown: str = Field(..., min_length=20)
    key_findings: List[str] = Field(default_factory=list)
    read_time_minutes: int = Field(default=10, ge=1)
    published_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class BenchmarkMetric(BaseModel):
    repository_id: str
    architecture_pattern: str
    avg_latency_ms: float
    cost_per_1k_tasks_usd: float
    resilience_score: int


class TeardownSearchHit(BaseModel):
    record_id: str
    slug: str
    title: str
    category: str
    snippet: str
    rank: float


class AgentQueryRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=1000)


class AgentQueryResponse(BaseModel):
    query_id: str
    query: str
    answer: str
    sources: List[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class RFC7807Error(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str
    instance: Optional[str] = None
