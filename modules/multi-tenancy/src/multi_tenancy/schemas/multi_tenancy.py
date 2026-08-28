"""Request/response models for `/v1/multi-tenancy/*` (LLD §3)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class RegisterTenantRequest(BaseModel):
    name: str
    tier: str = "standard"
    organisation_id: str | None = None


class SuspendTenantRequest(BaseModel):
    reason: str


class SuspendRequest(BaseModel):
    """Same shape as `SuspendTenantRequest` -- used by Organisation,
    Workspace, and Environment's own suspend endpoints, named generically
    since none of those three are tenant-specific."""

    reason: str


class TenantSchema(BaseModel):
    id: str
    name: str
    status: str
    tier: str
    organisation_id: str | None = None
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


class SetEntitlementsRequest(BaseModel):
    module_names: list[str]


class EntitlementListResponse(BaseModel):
    tenant_id: str
    module_names: list[str]
    configured: bool


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


# --- Organisation / Workspace / Environment (platform hierarchy control plane) ---


class RegisterOrganisationRequest(BaseModel):
    name: str
    owner_identity_id: str | None = None


class OrganisationSchema(BaseModel):
    id: str
    name: str
    status: str
    owner_identity_id: str | None = None
    labels: dict[str, str]
    version: int
    created_at: datetime
    updated_at: datetime


class OrganisationListResponse(BaseModel):
    items: list[OrganisationSchema]
    total: int
    limit: int
    offset: int


class RegisterWorkspaceRequest(BaseModel):
    tenant_id: str
    name: str
    owner_identity_id: str | None = None


class WorkspaceSchema(BaseModel):
    id: str
    tenant_id: str
    name: str
    status: str
    owner_identity_id: str | None = None
    labels: dict[str, str]
    version: int
    created_at: datetime
    updated_at: datetime


class WorkspaceListResponse(BaseModel):
    items: list[WorkspaceSchema]
    total: int
    limit: int
    offset: int


class RegisterEnvironmentRequest(BaseModel):
    workspace_id: str
    name: str
    kind: str = "development"
    region: str | None = None
    owner_identity_id: str | None = None


class EnvironmentSchema(BaseModel):
    id: str
    workspace_id: str
    name: str
    kind: str
    region: str | None = None
    status: str
    owner_identity_id: str | None = None
    labels: dict[str, str]
    version: int
    created_at: datetime
    updated_at: datetime


class EnvironmentListResponse(BaseModel):
    items: list[EnvironmentSchema]
    total: int
    limit: int
    offset: int
