"""Request/response models for `/v1/multi-tenancy/*` (LLD §3)."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


def _reject_null_byte(value: str) -> str:
    """Postgres's `text`/`varchar`/`json` columns are UTF-8 and reject the
    NUL byte outright (`asyncpg.exceptions.UntranslatableCharacterError`)
    -- a value `str` is happy to hold but the database is not. Schema-
    valid per OpenAPI (`type: string` says nothing about NUL), so
    nothing upstream of the DB call rejects it without this: caught
    here as a clean `422` instead of the request reaching the database
    at all (found by this module's own OpenAPI contract-test tier --
    the same fix Billing and Metering's own `_reject_null_byte` already
    established)."""
    if "\x00" in value:
        raise ValueError("must not contain a NUL byte (unsupported by Postgres's text encoding)")
    return value


def _reject_non_uuid(value: str) -> str:
    """`organisation_id` is a Postgres `UUID` foreign key; a syntactically
    invalid UUID is schema-valid per OpenAPI (`type: string` says nothing
    about UUID shape) but crashes with an unhandled
    `asyncpg.exceptions.DataError` deep in the driver instead of a clean
    `422` (found by this module's own OpenAPI contract-test tier -- the
    same class of bug Billing and Metering's own NUL-byte fix,
    `_reject_null_byte`, already established the pattern for)."""
    try:
        uuid.UUID(value)
    except ValueError as e:
        raise ValueError("organisation_id must be a valid UUID") from e
    return value


class RegisterTenantRequest(BaseModel):
    name: str
    tier: str = "standard"
    organisation_id: str | None = None

    @field_validator("name", "tier")
    @classmethod
    def _validate_no_null_byte(cls, value: str) -> str:
        return _reject_null_byte(value)

    @field_validator("organisation_id")
    @classmethod
    def _validate_organisation_id(cls, value: str | None) -> str | None:
        return _reject_non_uuid(value) if value is not None else value


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
    request this API accepts.

    `expected_version` was a bare `int` -- schema-valid per OpenAPI
    (`type: integer` says nothing about range) but `repository.py`'s own
    `_compare_and_swap` binds it straight into a `WHERE version =
    :expected_version` against `Organisation`/`Workspace`/`Environment`'s
    `version` column, a Postgres `INTEGER` (int4, max 2_147_483_647); any
    value at or above 2**31 crashed with an unhandled `asyncpg.DataError`
    instead of a clean `422` (found alongside LLM Gateway's identical
    unbounded-int4-column shape on its own `priority` field -- see that
    module's README). Bounded to `ge=0, le=1_000_000_000`, the same bound
    this platform's `offset` class already uses -- comfortably past any
    real version count, comfortably under the int4 overflow."""

    reason: str
    expected_version: int = Field(ge=0, le=1_000_000_000)


class VersionedRequest(BaseModel):
    """Body for Organisation/Workspace/Environment's reactivate/delete
    endpoints -- no other field needed, but `expected_version` is still
    required for the same real optimistic-concurrency reason
    `SuspendRequest` carries it. Bounded for the same int4-overflow reason
    documented on `SuspendRequest`."""

    expected_version: int = Field(ge=0, le=1_000_000_000)


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

    @field_validator("module_names")
    @classmethod
    def _validate_no_null_byte(cls, value: list[str]) -> list[str]:
        for item in value:
            _reject_null_byte(item)
        return value


class EntitlementListResponse(BaseModel):
    tenant_id: str
    module_names: list[str]
    configured: bool


class RunIsolationProbeRequest(BaseModel):
    tenant_id: str
    target_name: str

    @field_validator("tenant_id", "target_name")
    @classmethod
    def _validate_no_null_byte(cls, value: str) -> str:
        return _reject_null_byte(value)


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

    @field_validator("name", "owner_identity_id")
    @classmethod
    def _validate_no_null_byte(cls, value: str | None) -> str | None:
        return _reject_null_byte(value) if value is not None else value


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

    @field_validator("name", "owner_identity_id")
    @classmethod
    def _validate_no_null_byte(cls, value: str | None) -> str | None:
        return _reject_null_byte(value) if value is not None else value


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

    @field_validator("name", "kind", "region", "owner_identity_id")
    @classmethod
    def _validate_no_null_byte(cls, value: str | None) -> str | None:
        return _reject_null_byte(value) if value is not None else value


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

    @field_validator("limits")
    @classmethod
    def _validate_no_null_byte(cls, value: dict[str, float]) -> dict[str, float]:
        for key in value:
            _reject_null_byte(key)
        return value


class QuotaSetSchema(BaseModel):
    tenant_id: str
    limits: dict[str, float]
    configured: bool
    version: int
    updated_at: datetime | None = None


class SetResidencyPolicyRequest(BaseModel):
    allowed_regions: list[str]

    @field_validator("allowed_regions")
    @classmethod
    def _validate_no_null_byte(cls, value: list[str]) -> list[str]:
        for item in value:
            _reject_null_byte(item)
        return value


class ResidencyPolicySchema(BaseModel):
    tenant_id: str
    allowed_regions: list[str]
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

    @field_validator("resource_class")
    @classmethod
    def _validate_no_null_byte(cls, value: str) -> str:
        return _reject_null_byte(value)


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

    @field_validator("requested_by")
    @classmethod
    def _validate_requested_by(cls, value: str | None) -> str | None:
        return _reject_null_byte(value) if value is not None else value

    @field_validator("resources")
    @classmethod
    def _validate_resources_keys(cls, value: dict[str, float]) -> dict[str, float]:
        for key in value:
            _reject_null_byte(key)
        return value


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
    """`expected_version` bounded for the same int4-overflow reason
    documented on `SuspendRequest` -- `ResourceAllocation.version` is the
    same kind of Postgres `INTEGER` column."""

    approved_by: str
    expected_version: int = Field(ge=0, le=1_000_000_000)

    @field_validator("approved_by")
    @classmethod
    def _validate_no_null_byte(cls, value: str) -> str:
        return _reject_null_byte(value)


class RejectResourceAllocationRequest(BaseModel):
    """`expected_version` bounded for the same reason as
    `ApproveResourceAllocationRequest`."""

    reason: str
    expected_version: int = Field(ge=0, le=1_000_000_000)

    @field_validator("reason")
    @classmethod
    def _validate_no_null_byte(cls, value: str) -> str:
        return _reject_null_byte(value)
