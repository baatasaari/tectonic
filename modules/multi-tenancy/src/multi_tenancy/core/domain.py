"""Framework-agnostic domain objects (LLD §3 data model)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


def now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid.uuid4())


class TenantStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELETED = "deleted"


# The tenant lifecycle state machine (LLD §Level 3 "The tenant lifecycle state
# machine"): any transition not a value here is illegal and raises
# InvalidTransitionError -- the same shape Agent Marketplace, LLMOps, Deployment
# Strategy and PromptOps already established.
_LEGAL_TRANSITIONS: dict[TenantStatus, set[TenantStatus]] = {
    TenantStatus.ACTIVE: {TenantStatus.SUSPENDED, TenantStatus.DELETED},
    TenantStatus.SUSPENDED: {TenantStatus.ACTIVE, TenantStatus.DELETED},
    TenantStatus.DELETED: set(),
}


def is_legal_transition(from_status: TenantStatus, to_status: TenantStatus) -> bool:
    return to_status in _LEGAL_TRANSITIONS.get(from_status, set())


class HierarchyStatus(StrEnum):
    """Shared status type for Organisation/Workspace/Environment (LLD §Level 3
    "The platform hierarchy control plane", added for the independent
    architecture assessment's canonical resource model, §3.1). One shared
    enum and transition table across all three -- unlike TenantStatus, which
    stays its own separate type for backward compatibility, these three are
    net-new, identical in shape, and live in the same deployable, so sharing
    is the DRY choice, not the deployability-breaking one cross-module
    duplication elsewhere in this platform deliberately avoids."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELETED = "deleted"


_HIERARCHY_LEGAL_TRANSITIONS: dict[HierarchyStatus, set[HierarchyStatus]] = {
    HierarchyStatus.ACTIVE: {HierarchyStatus.SUSPENDED, HierarchyStatus.DELETED},
    HierarchyStatus.SUSPENDED: {HierarchyStatus.ACTIVE, HierarchyStatus.DELETED},
    HierarchyStatus.DELETED: set(),
}


def is_legal_hierarchy_transition(from_status: HierarchyStatus, to_status: HierarchyStatus) -> bool:
    return to_status in _HIERARCHY_LEGAL_TRANSITIONS.get(from_status, set())


class ResourceAllocationStatus(StrEnum):
    """`ResourceAllocation`'s own lifecycle (independent architecture
    assessment §5.2): a request either gets auto-approved immediately
    by policy or waits for a human decision -- see
    `ResourceAllocationService._within_auto_approve_threshold`. Both
    `ACTIVE` and `REJECTED` are terminal; a rejected request is
    resubmitted as a brand-new allocation, never reopened."""

    REQUESTED = "requested"
    ACTIVE = "active"
    REJECTED = "rejected"


# Resource-class naming convention this platform's quota enforcement relies on
# (QuotaEnforcementService): a class name ending in one of these suffixes gets a
# real, self-contained fixed-window counter (this module owns the state); every
# other class name is treated as capacity-shaped -- a stateless ceiling check
# against usage the caller reports, since the owning module (Vector DB for
# vector_count, etc.) is the real source of truth for its own current usage, not
# this one. See QuotaEnforcementService's own docstring.
_RATE_RESOURCE_CLASS_WINDOW_SECONDS: dict[str, int] = {
    "_per_second": 1,
    "_per_minute": 60,
    "_per_hour": 3600,
    "_per_day": 86400,
    "_daily": 86400,
}


def resource_class_window_seconds(resource_class: str) -> int | None:
    for suffix, seconds in _RATE_RESOURCE_CLASS_WINDOW_SECONDS.items():
        if resource_class.endswith(suffix):
            return seconds
    return None


def quota_window_start(at: datetime, window_seconds: int) -> datetime:
    """Real fixed-window bucketing: every timestamp within the same
    `window_seconds`-wide slice maps to the same `window_start`, so a
    new window resets the counter implicitly -- no cleanup job needed
    for correctness (a real counter-row garbage-collection job for old
    windows is separate, unbuilt work; see this module's README)."""
    epoch = int(at.timestamp())
    window_start_epoch = (epoch // window_seconds) * window_seconds
    return datetime.fromtimestamp(window_start_epoch, tz=UTC)


class TenantNotFoundError(Exception):
    def __init__(self, tenant_id: str) -> None:
        super().__init__(f"Tenant not found: {tenant_id}")


class OrganisationNotFoundError(Exception):
    def __init__(self, organisation_id: str) -> None:
        super().__init__(f"Organisation not found: {organisation_id}")


class WorkspaceNotFoundError(Exception):
    def __init__(self, workspace_id: str) -> None:
        super().__init__(f"Workspace not found: {workspace_id}")


class EnvironmentNotFoundError(Exception):
    def __init__(self, environment_id: str) -> None:
        super().__init__(f"Environment not found: {environment_id}")


class ResourceAllocationNotFoundError(Exception):
    def __init__(self, allocation_id: str) -> None:
        super().__init__(f"Resource allocation not found: {allocation_id}")


_AnyLifecycleStatus = TenantStatus | HierarchyStatus | ResourceAllocationStatus


class InvalidTransitionError(Exception):
    def __init__(self, from_status: _AnyLifecycleStatus, to_status: _AnyLifecycleStatus) -> None:
        super().__init__(f"Illegal transition: {from_status.value} -> {to_status.value}")
        self.from_status = from_status
        self.to_status = to_status


class ProbeTargetNotFoundError(Exception):
    def __init__(self, target_name: str) -> None:
        super().__init__(f"Unknown isolation probe target: {target_name}")


class OptimisticConcurrencyError(Exception):
    """Raised when a caller's `expected_version` no longer matches the
    row's real, current version -- someone else updated it first. Maps
    to a real `409 Conflict` at the API layer (`core/domain.py`'s own
    `InvalidTransitionError` maps to 409 too, but for a different
    reason: an illegal state transition versus a stale read; kept as
    two distinct exception types so a caller/route can tell which one
    happened and phrase the error correctly). Raised by the repository
    layer's real `WHERE version = :expected_version` compare-and-swap,
    never fabricated at the service layer from an in-memory guess --
    see `db/repository.py`'s `update_organisation`/`update_workspace`/
    `update_environment`/`update_resource_allocation`."""

    def __init__(self, *, expected_version: int) -> None:
        super().__init__(
            f"expected_version={expected_version} is stale -- this resource was updated by someone else first",
        )
        self.expected_version = expected_version


class ResidencyPolicyViolationError(Exception):
    """A new Environment's `region` is not in its tenant's configured
    `ResidencyPolicy.allowed_regions` -- raised by
    `EnvironmentService.register`, maps to a real `422 Unprocessable
    Entity` at the API layer (the request is well-formed, but this
    tenant's own residency policy forbids it)."""

    def __init__(self, *, tenant_id: str, region: str, allowed_regions: list[str]) -> None:
        super().__init__(
            f"region {region!r} is not permitted by tenant {tenant_id}'s residency policy "
            f"(allowed: {allowed_regions!r})",
        )
        self.tenant_id = tenant_id
        self.region = region
        self.allowed_regions = allowed_regions


@dataclass
class TenantRecord:
    # Deliberately has no `version` field, unlike OrganisationRecord/WorkspaceRecord/
    # EnvironmentRecord/ResourceAllocation -- those four are the assessment's net-new
    # canonical hierarchy/allocation objects and carry real optimistic-concurrency
    # enforcement (core/organisation_service.py's own docstring); TenantRecord predates
    # that work and stays its own, backward-compatible shape, the same reasoning
    # HierarchyStatus's own docstring gives for TenantStatus staying separate.
    id: str
    name: str
    status: TenantStatus = TenantStatus.ACTIVE
    tier: str = "standard"
    # `None` means this tenant isn't (yet) rolled up under an Organisation --
    # a real, valid, common state (most tenants in this platform's own test
    # data are standalone), not an oversight. See OrganisationRecord.
    organisation_id: str | None = None
    # `None` means this tenant's module entitlements have never been explicitly set --
    # ungated, every module allowed -- distinct from a real, explicit empty set (a plan
    # that includes zero modules), which denies everything. Set by
    # `replace_entitlements`, including when called with an empty list; see
    # `TenantRegistryService.gate`'s own docstring for how the two states differ.
    entitlements_configured_at: datetime | None = None
    created_at: datetime = field(default_factory=now)
    updated_at: datetime = field(default_factory=now)


@dataclass
class OrganisationRecord:
    """Top of the platform's real resource hierarchy (independent
    architecture assessment §3.1): `Organisation -> Tenant -> Workspace ->
    Environment`. An organisation is the billing/reporting umbrella a
    customer's multiple tenants (e.g. regional or business-unit
    subsidiaries) can roll up under -- optional, since most tenants in
    this platform have no need of one; see `TenantRecord.organisation_id`.
    """

    id: str
    name: str
    status: HierarchyStatus = HierarchyStatus.ACTIVE
    # The real Identity and Access identity accountable for this
    # organisation -- `None` is a valid, common state (not every
    # organisation has an owner assigned yet at creation time).
    owner_identity_id: str | None = None
    labels: dict[str, str] = field(default_factory=dict)
    # Optimistic-concurrency marker: incremented on every update. Not yet
    # enforced as a real compare-and-swap at the repository layer (that's
    # real, separate work -- see this module's README) -- present now so
    # the field exists on the wire and callers can start reading it.
    version: int = 1
    created_at: datetime = field(default_factory=now)
    updated_at: datetime = field(default_factory=now)


@dataclass
class WorkspaceRecord:
    """A logical grouping within one tenant (e.g. "Production
    workflows", "Marketing team") -- the platform hierarchy's second
    level. Always scoped to exactly one tenant; never independently
    movable between tenants (mirrors the assessment's provisioning model
    -- see this module's README for what's deliberately NOT built yet:
    workspace-to-environment resource allocation and quotas)."""

    id: str
    tenant_id: str
    name: str
    status: HierarchyStatus = HierarchyStatus.ACTIVE
    owner_identity_id: str | None = None
    labels: dict[str, str] = field(default_factory=dict)
    version: int = 1
    created_at: datetime = field(default_factory=now)
    updated_at: datetime = field(default_factory=now)


@dataclass
class EnvironmentRecord:
    """A deployable instance within one workspace (e.g. "production",
    "staging") -- the platform hierarchy's third level, the one real
    Agent Applications (Workflow Engine runs, Conversational Engine
    sessions, ...) are ultimately scoped under. `region` is a plain,
    unvalidated string today -- real residency *policy* (data-locality
    enforcement, not just a label) is real, separate, unbuilt work; see
    this module's README."""

    id: str
    workspace_id: str
    name: str
    kind: str = "development"  # free string: production | staging | development | ...
    region: str | None = None
    status: HierarchyStatus = HierarchyStatus.ACTIVE
    owner_identity_id: str | None = None
    labels: dict[str, str] = field(default_factory=dict)
    version: int = 1
    created_at: datetime = field(default_factory=now)
    updated_at: datetime = field(default_factory=now)


@dataclass
class IsolationProbeResult:
    id: str
    tenant_id: str
    target_name: str
    passed: bool
    breach_count: int
    sample_size: int
    details: str
    checked_at: datetime = field(default_factory=now)


@dataclass
class TenantGateResult:
    allowed: bool
    reason: str


@dataclass
class TenantEntitlementRecord:
    """One (tenant, module) feature flag: does this tenant's subscription
    include this module. `replace_entitlements` is the only write path --
    a tenant's entitlement set is always replaced wholesale (mirroring
    the pricing plan it's derived from), never patched field-by-field, so
    there's never a stale flag left behind after a plan change drops a
    module."""

    tenant_id: str
    module_name: str
    updated_at: datetime = field(default_factory=now)


@dataclass
class QuotaSet:
    """Per-tenant resource-class limits -- the ceiling side of quota
    enforcement (independent architecture assessment §5.2's "canonical
    allocation object" made concrete at the tenant level). `limits` keys
    are resource-class names (e.g. `"requests_per_minute"`,
    `"tokens_per_minute"`, `"workflow_concurrency"`, `"storage_gb"`,
    `"vector_count"`, `"model_spend_daily_usd"`) mapped to a numeric
    limit; see `resource_class_window_seconds` for which of those get a
    real rate-counter versus a capacity-ceiling check.
    `configured_at` is `None` until a tenant's quotas are first set --
    the same rollout-safety default `TenantRecord.entitlements_configured_at`
    established: an unconfigured tenant is unlimited, not silently
    throttled to zero, so shipping quota enforcement never breaks a
    tenant that predates it."""

    tenant_id: str
    limits: dict[str, float] = field(default_factory=dict)
    configured_at: datetime | None = None
    version: int = 1
    updated_at: datetime = field(default_factory=now)


@dataclass
class ResidencyPolicy:
    """Per-tenant data-residency policy (independent architecture
    assessment §3.4 point 5: "quota, budget, residency, and risk
    policies permit execution") -- `allowed_regions` is the set of
    `EnvironmentRecord.region` values a new Environment under this
    tenant may register into, enforced for real by
    `EnvironmentService.register` (`core/environment_service.py`).
    Scoped to Tenant, not Organisation -- the same level `QuotaSet`
    already uses, and the level `region` itself actually lives one
    step below (Workspace -> Environment); an Organisation-wide
    default/inheritance story is real, separate, unbuilt work.
    `configured_at` is `None` until a tenant's policy is first set --
    the same rollout-safety default `QuotaSet.configured_at`/
    `TenantRecord.entitlements_configured_at` already establish: an
    unconfigured tenant has no residency restriction at all, not
    silently locked out of every region, so shipping this check never
    breaks a tenant that predates it."""

    tenant_id: str
    allowed_regions: list[str] = field(default_factory=list)
    configured_at: datetime | None = None
    version: int = 1
    updated_at: datetime = field(default_factory=now)


@dataclass
class QuotaCheckResult:
    allowed: bool
    resource_class: str
    limit: float | None
    used: float
    remaining: float | None
    reason: str


@dataclass
class ResourceAllocation:
    """The independent architecture assessment's own §5.2 "canonical
    allocation object", scoped to one Environment: the reserved/approved
    capacity across every resource dimension it names (CPU/memory/GPU,
    replicas, concurrent runs, requests/tokens per minute, model spend,
    workflow concurrency, storage, vector count, ingestion volume,
    retention, ...) -- kept as a flexible `resources: dict[str, float]`
    rather than one field per dimension, the same shape `QuotaSet.limits`
    already uses, so both share one resource-class vocabulary. A real
    request -> automated-or-manual-approval -> active lifecycle (§5.2's
    "submit requested quota -> automated policy decision -> approval if
    threshold exceeded"), not just a data bag -- see
    `ResourceAllocationService._within_auto_approve_threshold` for the
    actual policy decision.

    What this deliberately does NOT do yet (see this module's README):
    reconcile the approved numbers against real Kubernetes/database/
    vector capacity, real regional capacity checks, or a real billing
    amendment -- this module owns the *approved intent*, not enforcement
    against live infrastructure."""

    id: str
    environment_id: str
    resources: dict[str, float] = field(default_factory=dict)
    reserved_capacity: bool = False
    status: ResourceAllocationStatus = ResourceAllocationStatus.REQUESTED
    requested_by: str | None = None
    approved_by: str | None = None
    rejection_reason: str | None = None
    version: int = 1
    created_at: datetime = field(default_factory=now)
    updated_at: datetime = field(default_factory=now)
