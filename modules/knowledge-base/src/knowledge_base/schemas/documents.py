"""Request/response models for `/v1/knowledge-base/*` (LLD §3)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class DocumentVersionSchema(BaseModel):
    id: str
    document_id: str
    content_hash: str
    version_number: int
    created_by: str
    created_at: datetime


class DocumentSchema(BaseModel):
    id: str
    tenant_id: str
    title: str
    source_type: str
    current_version_id: str | None
    status: str
    last_reviewed_at: datetime
    created_at: datetime


class DocumentWithVersionsSchema(DocumentSchema):
    versions: list[DocumentVersionSchema]


class IngestResponse(BaseModel):
    document: DocumentSchema
    version: DocumentVersionSchema
    chunk_count: int


class ChunkSchema(BaseModel):
    id: str
    document_version_id: str
    content: str
    chunk_index: int
    policy_tags: list[str]
    token_count: int


class ChunkListResponse(BaseModel):
    items: list[ChunkSchema]
    total: int
    limit: int
    offset: int


class ReviewRequest(BaseModel):
    reviewed_by: str


class ReviewResponse(BaseModel):
    last_reviewed_at: datetime
    status: str
