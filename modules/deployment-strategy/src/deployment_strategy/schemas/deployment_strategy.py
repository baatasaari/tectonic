"""Request/response models for `/v1/deployment-strategy/*` (LLD §3)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class DeployRequest(BaseModel):
    service_name: str
    build_ref: str
    target: str
    canary_percentage: int = 10
    budget_policy_id: str | None = None


class RollbackRequest(BaseModel):
    reason: str


class DeploymentSchema(BaseModel):
    id: str
    tenant_id: str
    service_name: str
    build_ref: str
    target: str
    canary_percentage: int
    budget_policy_id: str | None
    stage: str
    started_at: datetime
    promoted_at: datetime | None
    rolled_back_at: datetime | None
    rollback_reason: str | None
    created_at: datetime
    updated_at: datetime


class DeploymentListResponse(BaseModel):
    items: list[DeploymentSchema]
    total: int
    limit: int
    offset: int


class CanaryHealthResultSchema(BaseModel):
    groundedness_score: float | None
    cost_score: float | None
    composite_score: float | None
    passed: bool
    reason: str
