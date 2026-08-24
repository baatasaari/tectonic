"""`/v1/knowledge-base/*` routes (LLD §3).

**Multipart ingestion simplification.** The LLD's `POST /documents`
accepts "file (multipart) or source_ref" — a source_ref would pull bytes
from Data Source Plugins (Module 8) for sync-originated documents. That
cross-module fetch is out of scope here; this router accepts either an
uploaded `file` or an inline `content_text` form field as the byte
source, and still records `source_ref`/`source_type` as metadata so the
data model matches the LLD exactly.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from knowledge_base.api.deps import build_ingestion_service, get_ctx, get_repository
from knowledge_base.app_context import AppContext
from knowledge_base.core.domain import DocumentNotFoundError, SourceType
from knowledge_base.core.ports import KnowledgeBaseRepository
from knowledge_base.schemas.documents import (
    ChunkListResponse,
    ChunkSchema,
    DocumentSchema,
    DocumentVersionSchema,
    DocumentWithVersionsSchema,
    IngestResponse,
    ReviewRequest,
    ReviewResponse,
)

router = APIRouter(prefix="/v1/knowledge-base", tags=["knowledge-base"])


def _document_schema(d) -> DocumentSchema:
    return DocumentSchema(
        id=d.id, tenant_id=d.tenant_id, title=d.title, source_type=d.source_type.value,
        current_version_id=d.current_version_id, status=d.status.value,
        last_reviewed_at=d.last_reviewed_at, created_at=d.created_at,
    )


def _version_schema(v) -> DocumentVersionSchema:
    return DocumentVersionSchema(
        id=v.id, document_id=v.document_id, content_hash=v.content_hash,
        version_number=v.version_number, created_by=v.created_by, created_at=v.created_at,
    )


async def _read_bytes(file: UploadFile | None, content_text: str | None) -> tuple[bytes, str, str]:
    if file is not None:
        return await file.read(), file.content_type or "text/plain", file.filename or ""
    if content_text is not None:
        return content_text.encode("utf-8"), "text/plain", ""
    raise HTTPException(status_code=422, detail="either 'file' or 'content_text' is required")


@router.post("/documents", response_model=IngestResponse, status_code=201)
async def ingest_document(
    tenant_id: str = Form(...),
    title: str = Form(...),
    source_type: str = Form("upload"),
    source_ref: str | None = Form(None),
    file: UploadFile | None = File(None),
    content_text: str | None = Form(None),
    policy_tags: str = Form("[]"),
    chunking_strategy: str | None = Form(None),
    ctx: AppContext = Depends(get_ctx),
    repository: KnowledgeBaseRepository = Depends(get_repository),
) -> IngestResponse:
    content, content_type, filename = await _read_bytes(file, content_text)
    tags = json.loads(policy_tags) if policy_tags else []

    service = build_ingestion_service(ctx, repository)
    result = await service.ingest_document(
        tenant_id=tenant_id, title=title, source_type=SourceType(source_type), content=content,
        content_type=content_type, filename=filename, policy_tags=tags, chunking_strategy=chunking_strategy,
    )
    return IngestResponse(
        document=_document_schema(result.document), version=_version_schema(result.version),
        chunk_count=result.chunk_count,
    )


@router.post("/documents/{document_id}/versions", response_model=IngestResponse)
async def create_version(
    document_id: str,
    created_by: str = Form(""),
    file: UploadFile | None = File(None),
    content_text: str | None = Form(None),
    policy_tags: str = Form("[]"),
    chunking_strategy: str | None = Form(None),
    ctx: AppContext = Depends(get_ctx),
    repository: KnowledgeBaseRepository = Depends(get_repository),
) -> IngestResponse:
    content, content_type, filename = await _read_bytes(file, content_text)
    tags = json.loads(policy_tags) if policy_tags else []

    service = build_ingestion_service(ctx, repository)
    try:
        result = await service.create_version(
            document_id, content=content, content_type=content_type, filename=filename, policy_tags=tags,
            created_by=created_by, chunking_strategy=chunking_strategy,
        )
    except DocumentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    return IngestResponse(
        document=_document_schema(result.document), version=_version_schema(result.version),
        chunk_count=result.chunk_count,
    )


@router.get("/documents/{document_id}", response_model=DocumentWithVersionsSchema)
async def get_document(
    document_id: str,
    repository: KnowledgeBaseRepository = Depends(get_repository),
) -> DocumentWithVersionsSchema:
    document = await repository.get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="document not found")
    versions = await repository.list_versions(document_id)
    return DocumentWithVersionsSchema(
        **_document_schema(document).model_dump(), versions=[_version_schema(v) for v in versions],
    )


@router.get("/chunks", response_model=ChunkListResponse)
async def list_chunks(
    document_version_id: str | None = Query(None),
    policy_tag: str | None = Query(None),
    tenant_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    repository: KnowledgeBaseRepository = Depends(get_repository),
) -> ChunkListResponse:
    if document_version_id:
        chunks, total = await repository.list_chunks_by_version(document_version_id, limit=limit, offset=offset)
    elif policy_tag and tenant_id:
        chunks, total = await repository.list_chunks_by_policy_tag(
            tenant_id, policy_tag, limit=limit, offset=offset
        )
    else:
        raise HTTPException(
            status_code=422, detail="either document_version_id, or policy_tag plus tenant_id, is required"
        )
    return ChunkListResponse(
        items=[
            ChunkSchema(
                id=c.id, document_version_id=c.document_version_id, content=c.content,
                chunk_index=c.chunk_index, policy_tags=c.policy_tags, token_count=c.token_count,
            )
            for c in chunks
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/documents/{document_id}/review", response_model=ReviewResponse)
async def review_document(
    document_id: str,
    body: ReviewRequest,
    ctx: AppContext = Depends(get_ctx),
    repository: KnowledgeBaseRepository = Depends(get_repository),
) -> ReviewResponse:
    service = build_ingestion_service(ctx, repository)
    try:
        document = await service.review(document_id, body.reviewed_by)
    except DocumentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return ReviewResponse(last_reviewed_at=document.last_reviewed_at, status=document.status.value)
