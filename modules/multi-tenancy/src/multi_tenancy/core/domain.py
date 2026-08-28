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


class InvalidTransitionError(Exception):
    def __init__(self, from_status: TenantStatus | HierarchyStatus, to_status: TenantStatus | HierarchyStatus) -> None:
        super().__init__(f"Illegal transition: {from_status.value} -> {to_status.value}")
        self.from_status = from_status
        self.to_status = to_status


class ProbeTargetNotFoundError(Exception):
    def __init__(self, target_name: str) -> None:
        super().__init__(f"Unknown isolation probe target: {target_name}")


@dataclass
class TenantRecord:
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
