"""Request/response models for `/v1/vector-db/*` (LLD §3)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class IndexPointRequest(BaseModel):
    tenant_id: str
    source_module: str
    source_ref: str
    content: str | None = None
    vector: list[float] | None = None
    payload: dict[str, Any] = {}
    embedding_model_version: str | None = None


class IndexPointResponse(BaseModel):
    id: str


class DeleteResponse(BaseModel):
    status: str


class QueryRequest(BaseModel):
    tenant_id: str
    text: str | None = None
    vector: list[float] | None = None
    filters: dict[str, Any] = {}
    top_k: int | None = None
    hybrid: bool | None = None


class ScoredResultSchema(BaseModel):
    id: str
    score: float
    payload: dict[str, Any]


class QueryResponse(BaseModel):
    results: list[ScoredResultSchema]


class StartMigrationRequest(BaseModel):
    tenant_id: str
    new_embedding_model: str


class MigrationResponse(BaseModel):
    migration_id: str
    status: str


class MigrationStatusResponse(BaseModel):
    migration_id: str
    status: str
    progress: float
    points_total: int
    points_migrated: int
    created_at: datetime
    completed_at: datetime | None
