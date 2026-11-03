"""Document ingestion and catalog management endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.config import Settings, get_settings
from app.database import (
    delete_document,
    get_document,
    list_documents,
    save_document,
    save_documents_batch,
)
from app.models import (
    DocumentBatchCreate,
    DocumentCreate,
    DocumentListResponse,
    DocumentResponse,
)

router = APIRouter(prefix="/api/v1/documents", tags=["Documents"])


@router.post(
    "",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a new document into SQLite WAL and FTS5 index",
)
@router.post(
    "/ingest",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=True,
    summary="Ingest document alias",
)
async def ingest_document(
    doc: DocumentCreate,
    settings: Settings = Depends(get_settings),
) -> DocumentResponse:
    """Ingest a single document into the SQLite database with FTS5 triggers."""
    saved = await save_document(doc.model_dump(), settings.database_path)
    return DocumentResponse(**saved)


@router.post(
    "/batch",
    response_model=list[DocumentResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Batch ingest multiple documents into SQLite WAL and FTS5 index",
)
async def ingest_batch_documents(
    batch: DocumentBatchCreate,
    settings: Settings = Depends(get_settings),
) -> list[DocumentResponse]:
    """Ingest multiple documents into the SQLite database."""
    docs_data = [d.model_dump() for d in batch.documents]
    saved_list = await save_documents_batch(docs_data, settings.database_path)
    return [DocumentResponse(**d) for d in saved_list]


@router.get(
    "/{doc_id}",
    response_model=DocumentResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve a document by ID",
)
async def get_document_by_id(
    doc_id: str,
    settings: Settings = Depends(get_settings),
) -> DocumentResponse:
    """Fetch an individual document by its unique identifier."""
    doc = await get_document(doc_id, settings.database_path)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{doc_id}' not found",
        )
    return DocumentResponse(**doc)


@router.get(
    "",
    response_model=DocumentListResponse,
    status_code=status.HTTP_200_OK,
    summary="List ingested documents with pagination",
)
async def list_all_documents(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    settings: Settings = Depends(get_settings),
) -> DocumentListResponse:
    """Retrieve paginated catalog of stored documents."""
    docs = await list_documents(
        limit=limit, offset=offset, db_path=settings.database_path
    )
    return DocumentListResponse(documents=[DocumentResponse(**d) for d in docs], total=len(docs))


@router.delete(
    "/{doc_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a document by ID",
)
async def remove_document(
    doc_id: str,
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    """Remove a document from the database, automatically updating FTS5 index."""
    deleted = await delete_document(doc_id, settings.database_path)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{doc_id}' not found for deletion",
        )
    return {"message": f"Document '{doc_id}' deleted successfully"}
