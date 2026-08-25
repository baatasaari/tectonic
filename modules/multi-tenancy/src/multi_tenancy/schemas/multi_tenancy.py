"""Request/response models for `/v1/multi-tenancy/*` (LLD §3)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class RegisterTenantRequest(BaseModel):
    name: str
    tier: str = "standard"


class SuspendTenantRequest(BaseModel):
    reason: str


class TenantSchema(BaseModel):
    id: str
    name: str
    status: str
    tier: str
    created_at: datetime
    updated_at: datetime


class TenantListResponse(BaseModel):
    items: list[TenantSchema]
    total: int
    limit: int
    offset: int


class TenantGateResultSchema(BaseModel):
    allowed: bool
    reason: str


class RunIsolationProbeRequest(BaseModel):
    tenant_id: str
    target_name: str


class IsolationProbeResultSchema(BaseModel):
    id: str
    tenant_id: str
    target_name: str
    passed: bool
    breach_count: int
    sample_size: int
    details: str
    checked_at: datetime


class IsolationProbeResultListResponse(BaseModel):
    items: list[IsolationProbeResultSchema]
    total: int
    limit: int
    offset: int
