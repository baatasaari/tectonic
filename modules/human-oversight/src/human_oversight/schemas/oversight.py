"""Request/response models for `/v1/human-oversight/*` (LLD §3)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class CreateRequestRequest(BaseModel):
    tenant_id: str
    requesting_module: str
    requesting_ref: str
    context: dict[str, Any] = {}
    priority: str = "medium"
    timeout_seconds: int | None = None


class OversightRequestSchema(BaseModel):
    id: str
    tenant_id: str
    requesting_module: str
    requesting_ref: str
    context: dict[str, Any]
    priority: str
    status: str
    claimed_by: str | None
    created_at: datetime
    expires_at: datetime


class OversightRequestListResponse(BaseModel):
    items: list[OversightRequestSchema]
    total: int
    limit: int
    offset: int


class ClaimRequest(BaseModel):
    claimed_by: str


class ClaimResponse(BaseModel):
    status: str


class DecideRequest(BaseModel):
    decision: str
    decided_by: str
    decision_reason: str = ""
    override_details: dict[str, Any] | None = None


class DecisionSchema(BaseModel):
    id: str
    request_id: str
    decision: str
    decided_by: str
    decision_reason: str
    decided_at: datetime


class OversightRequestDetailSchema(OversightRequestSchema):
    decision: DecisionSchema | None = None
