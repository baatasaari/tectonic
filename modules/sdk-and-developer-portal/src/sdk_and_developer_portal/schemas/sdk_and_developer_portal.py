"""Request/response models for `/v1/sdk-portal/*` (LLD §3)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class RegisterDeveloperRequest(BaseModel):
    name: str
    email: str
    role_names: list[str] = []


class DeveloperAccountSchema(BaseModel):
    id: str
    name: str
    email: str
    tenant_id: str
    identity_id: str
    status: str
    created_at: datetime
    updated_at: datetime


class DeveloperAccountListResponse(BaseModel):
    items: list[DeveloperAccountSchema]
    total: int
    limit: int
    offset: int


class IssueSandboxTokenRequest(BaseModel):
    requested_scopes: list[str] | None = None


class IssuedTokenSchema(BaseModel):
    token: str
    granted_scopes: list[str]


class ModuleCatalogEntrySchema(BaseModel):
    module_name: str
    base_url: str
    title: str
    version: str
    path_count: int
    spec_json: dict[str, Any]
    spec_hash: str
    last_synced_at: datetime


class ModuleCatalogListResponse(BaseModel):
    items: list[ModuleCatalogEntrySchema]
    total: int
    limit: int
    offset: int


class GenerateSdkRequest(BaseModel):
    module_name: str
    language: str = "python"


class SdkPackageSchema(BaseModel):
    id: str
    module_name: str
    language: str
    version: int
    source_code: str
    spec_hash: str
    generated_at: datetime


class SdkPackageListResponse(BaseModel):
    items: list[SdkPackageSchema]
    total: int
    limit: int
    offset: int


class AdoptionMetricsSchema(BaseModel):
    first_call_at: datetime | None
    time_to_first_call_seconds: float | None


class AdoptionRateSchema(BaseModel):
    adopted_count: int
    total_developers: int
    rate: float | None
