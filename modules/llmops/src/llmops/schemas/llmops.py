"""Request/response models for `/v1/llmops/*` (LLD §3)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class RegisterModelVersionRequest(BaseModel):
    model_name: str
    version: str
    artifact_ref: str


class ModelVersionSchema(BaseModel):
    id: str
    tenant_id: str
    model_name: str
    version: str
    artifact_ref: str
    status: str
    created_at: datetime


class ModelVersionListResponse(BaseModel):
    items: list[ModelVersionSchema]
    total: int
    limit: int
    offset: int


class StartCanaryRequest(BaseModel):
    model_version_id: str
    target: str
    canary_percentage: int = 10


class RollbackRequest(BaseModel):
    reason: str


class DeploymentSchema(BaseModel):
    id: str
    tenant_id: str
    model_version_id: str
    model_name: str
    target: str
    canary_percentage: int
    stage: str
    started_at: datetime
    promoted_at: datetime | None
    rolled_back_at: datetime | None
    rollback_reason: str | None
    created_at: datetime
    updated_at: datetime


class CanaryGateResultSchema(BaseModel):
    sample_size: int
    pass_rate: float | None
    passed: bool
    reason: str
