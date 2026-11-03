"""Tier 4: FastAPI TestClient HTTP contract and endpoint integration tests."""

from typing import Any
import pytest
from fastapi.testclient import TestClient


@pytest.mark.api
class TestHealthEndpoints:
    """Validate liveness and readiness probe HTTP contracts."""

    def test_liveness_endpoint(self, test_client: TestClient) -> None:
        resp = test_client.get("/health/live")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "live"
        assert "timestamp" in data

    def test_readiness_endpoint(self, test_client: TestClient) -> None:
        resp = test_client.get("/health/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ready"
        assert data["journal_mode"].lower() == "wal"

    def test_root_endpoint(self, test_client: TestClient) -> None:
        resp = test_client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert "service" in data
        assert "api_endpoints" in data


@pytest.mark.api
class TestDocumentEndpoints:
    """Validate document ingestion, retrieval, and catalog management endpoints."""

    def test_ingest_document(self, test_client: TestClient) -> None:
        payload = {
            "title": "API Test Document",
            "content": "Testing document ingestion over HTTP.",
            "metadata": {"test": True},
        }
        resp = test_client.post("/api/v1/documents", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "API Test Document"
        assert data["id"].startswith("doc_")
        assert data["metadata"]["test"] is True

    def test_ingest_document_alias(self, test_client: TestClient) -> None:
        payload = {
            "title": "Alias Test",
            "content": "Testing ingest alias endpoint.",
        }
        resp = test_client.post("/api/v1/documents/ingest", json=payload)
        assert resp.status_code == 201
        assert resp.json()["title"] == "Alias Test"

    def test_batch_ingest_documents(self, test_client: TestClient) -> None:
        payload = {
            "documents": [
                {"title": "Batch Doc 1", "content": "Content for batch 1"},
                {"title": "Batch Doc 2", "content": "Content for batch 2"},
            ]
        }
        resp = test_client.post("/api/v1/documents/batch", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert len(data) == 2

    def test_get_document_by_id(self, test_client: TestClient) -> None:
        # Ingest first
        doc = test_client.post(
            "/api/v1/documents",
            json={"title": "To Fetch", "content": "Fetchable content."},
        ).json()

        resp = test_client.get(f"/api/v1/documents/{doc['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == doc["id"]

    def test_get_nonexistent_document_returns_404(self, test_client: TestClient) -> None:
        resp = test_client.get("/api/v1/documents/nonexistent_id_999")
        assert resp.status_code == 404
        data = resp.json()
        assert data["status"] == 404
        assert "not found" in data["detail"].lower()

    def test_list_documents(self, test_client: TestClient) -> None:
        test_client.post("/api/v1/documents", json={"title": "Doc A", "content": "AAA"})
        test_client.post("/api/v1/documents", json={"title": "Doc B", "content": "BBB"})

        resp = test_client.get("/api/v1/documents?limit=10&offset=0")
        assert resp.status_code == 200
        data = resp.json()
        assert "documents" in data
        assert data["total"] >= 2

    def test_delete_document(self, test_client: TestClient) -> None:
        doc = test_client.post(
            "/api/v1/documents",
            json={"title": "To Delete", "content": "Delete me."},
        ).json()

        del_resp = test_client.delete(f"/api/v1/documents/{doc['id']}")
        assert del_resp.status_code == 200

        # Verify 404 on subsequent get
        assert test_client.get(f"/api/v1/documents/{doc['id']}").status_code == 404

    def test_delete_nonexistent_document_returns_404(self, test_client: TestClient) -> None:
        resp = test_client.delete("/api/v1/documents/missing_doc_xyz")
        assert resp.status_code == 404


@pytest.mark.api
class TestRAGEndpoints:
    """Validate direct FTS5 search and complete LangGraph RAG reasoning endpoints."""

    def test_direct_fts5_search_get(
        self, test_client: TestClient, sample_docs: list[dict[str, Any]]
    ) -> None:
        resp = test_client.get("/api/v1/rag/search?q=WAL")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_results"] >= 1
        assert any("WAL" in r["title"] or "WAL" in r["content"] for r in data["results"])

    def test_direct_fts5_search_post(
        self, test_client: TestClient, sample_docs: list[dict[str, Any]]
    ) -> None:
        resp = test_client.post(
            "/api/v1/rag/search", json={"query": "FTS5", "limit": 5}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_results"] >= 1

    def test_rag_query_endpoint_e2e(
        self, test_client: TestClient, sample_docs: list[dict[str, Any]]
    ) -> None:
        payload = {
            "query": "How does SQLite WAL mode work?",
            "top_k": 3,
            "threshold": 0.0,
            "enable_decomposition": True,
            "max_iterations": 2,
        }
        resp = test_client.post("/api/v1/rag/query", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["completed"] is True
        assert data["is_relevant"] is True
        assert len(data["retrieved_docs"]) > 0
        assert len(data["citations"]) > 0
        assert "WAL" in data["answer"]

    def test_rag_query_validation_error_rfc7807(self, test_client: TestClient) -> None:
        # Empty query string violates min_length=1
        resp = test_client.post("/api/v1/rag/query", json={"query": ""})
        assert resp.status_code == 422
        data = resp.json()
        assert data["status"] == 422
        assert data["title"] == "Request Validation Error"
