"""Request/response models for `/v1/agent-marketplace/*` (LLD §3)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class SubmitListingRequest(BaseModel):
    agent_card_id: str
    submitted_by: str = ""
    external_listing_enabled: bool = False


class RejectListingRequest(BaseModel):
    reviewed_by: str = ""
    reason: str


class ApproveListingRequest(BaseModel):
    reviewed_by: str = ""


class RecordUsageRequest(BaseModel):
    consumer_tenant_id: str


class ListingSchema(BaseModel):
    id: str
    tenant_id: str
    agent_card_id: str
    name: str
    description: str
    skills_snapshot: list[dict[str, Any]]
    trust_score_snapshot: float | None
    status: str
    submitted_by: str
    reviewed_by: str | None
    reviewed_at: datetime | None
    rejection_reason: str | None
    reuse_count: int
    external_listing_enabled: bool
    created_at: datetime
    updated_at: datetime


class ListingListResponse(BaseModel):
    items: list[ListingSchema]
    total: int
    limit: int
    offset: int


class ReuseMetricsSchema(BaseModel):
    reuse_count: int
    distinct_consumer_tenants: int
