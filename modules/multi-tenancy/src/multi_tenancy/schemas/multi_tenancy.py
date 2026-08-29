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
    """Used by Organisation, Workspace, and Environment's own suspend
    endpoints, named generically since none of those three are
    tenant-specific -- unlike `SuspendTenantRequest`, this also carries
    `expected_version`: real optimistic-concurrency control (these
    three record types carry a real `version` field; `TenantRecord`
    deliberately doesn't -- see `core/domain.py`). The caller's last-
    known version is required, not optional: mutating a resource blind,
    with no idea whether it changed since you last read it, isn't a
    request this API accepts."""

    reason: str
    expected_version: int


class VersionedRequest(BaseModel):
    """Body for Organisation/Workspace/Environment's reactivate/delete
    endpoints -- no other field needed, but `expected_version` is still
    required for the same real optimistic-concurrency reason
    `SuspendRequest` carries it."""

    expected_version: int


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


# --- Quota Set / real-time quota enforcement ---


class SetQuotaLimitsRequest(BaseModel):
    limits: dict[str, float]


class QuotaSetSchema(BaseModel):
    tenant_id: str
    limits: dict[str, float]
    configured: bool
    version: int
    updated_at: datetime | None = None


class QuotaCheckRequest(BaseModel):
    resource_class: str
    amount: float = 1.0
    # Required only for a capacity-shaped resource class (one not ending
    # `_per_minute`/`_per_second`/`_per_hour`/`_per_day`/`_daily`) -- see
    # QuotaEnforcementService's own docstring for why this module can't
    # track that usage itself.
    current_usage: float | None = None


class QuotaCheckResultSchema(BaseModel):
    allowed: bool
    resource_class: str
    limit: float | None
    used: float
    remaining: float | None
    reason: str


# --- Resource Allocation ---


class RequestResourceAllocationRequest(BaseModel):
    environment_id: str
    resources: dict[str, float]
    reserved_capacity: bool = False
    requested_by: str | None = None


class ResourceAllocationSchema(BaseModel):
    id: str
    environment_id: str
    resources: dict[str, float]
    reserved_capacity: bool
    status: str
    requested_by: str | None = None
    approved_by: str | None = None
    rejection_reason: str | None = None
    version: int
    created_at: datetime
    updated_at: datetime


class ResourceAllocationListResponse(BaseModel):
    items: list[ResourceAllocationSchema]
    total: int
    limit: int
    offset: int


class ApproveResourceAllocationRequest(BaseModel):
    approved_by: str
    expected_version: int


class RejectResourceAllocationRequest(BaseModel):
    reason: str
    expected_version: int
