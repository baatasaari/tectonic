"""Abstract ports this module depends on: persistence, the Auditability
peer, and the one generic client shape the Isolation Probe Service
reuses against every registered platform module.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from multi_tenancy.core.domain import (
    EnvironmentRecord,
    HierarchyStatus,
    IsolationProbeResult,
    OrganisationRecord,
    QuotaSet,
    ResourceAllocation,
    ResourceAllocationStatus,
    TenantEntitlementRecord,
    TenantRecord,
    TenantStatus,
    WorkspaceRecord,
)


class MultiTenancyRepository(Protocol):
    async def create_tenant(self, record: TenantRecord) -> TenantRecord: ...

    async def get_tenant(self, tenant_id: str) -> TenantRecord | None: ...

    async def update_tenant(self, record: TenantRecord) -> TenantRecord: ...

    async def list_tenants(
        self, *, status: TenantStatus | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[TenantRecord], int]: ...

    async def create_probe_result(self, record: IsolationProbeResult) -> IsolationProbeResult: ...

    async def list_probe_results(
        self, *, tenant_id: str | None = None, target_name: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[IsolationProbeResult], int]: ...

    async def replace_entitlements(
        self, *, tenant_id: str, module_names: list[str],
    ) -> list[TenantEntitlementRecord]:
        """Wholesale replace: deletes every existing entitlement row for
        this tenant, inserts one per `module_names`, and stamps the
        tenant's own `entitlements_configured_at` -- even when
        `module_names` is empty, since that's a real, meaningful state
        (see `TenantRecord.entitlements_configured_at`'s docstring)."""
        ...

    async def list_entitlements(self, tenant_id: str) -> list[TenantEntitlementRecord]: ...

    # --- Organisation / Workspace / Environment (platform hierarchy control plane) ---

    async def create_organisation(self, record: OrganisationRecord) -> OrganisationRecord: ...

    async def get_organisation(self, organisation_id: str) -> OrganisationRecord | None: ...

    async def update_organisation(self, record: OrganisationRecord) -> OrganisationRecord: ...

    async def list_organisations(
        self, *, status: HierarchyStatus | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[OrganisationRecord], int]: ...

    async def create_workspace(self, record: WorkspaceRecord) -> WorkspaceRecord: ...

    async def get_workspace(self, workspace_id: str) -> WorkspaceRecord | None: ...

    async def update_workspace(self, record: WorkspaceRecord) -> WorkspaceRecord: ...

    async def list_workspaces(
        self, *, tenant_id: str | None = None, status: HierarchyStatus | None = None,
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[WorkspaceRecord], int]: ...

    async def create_environment(self, record: EnvironmentRecord) -> EnvironmentRecord: ...

    async def get_environment(self, environment_id: str) -> EnvironmentRecord | None: ...

    async def update_environment(self, record: EnvironmentRecord) -> EnvironmentRecord: ...

    async def list_environments(
        self, *, workspace_id: str | None = None, status: HierarchyStatus | None = None,
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[EnvironmentRecord], int]: ...

    # --- Quota Set / real-time quota enforcement ---

    async def get_quota_set(self, tenant_id: str) -> QuotaSet | None: ...

    async def upsert_quota_set(self, *, tenant_id: str, limits: dict[str, float]) -> QuotaSet:
        """Wholesale replace, the same pattern `replace_entitlements`
        already established: one row per tenant, the whole `limits`
        dict is always replaced together, never patched key by key."""
        ...

    async def increment_quota_counter(
        self, *, tenant_id: str, resource_class: str, amount: float, window_seconds: int, now: datetime,
    ) -> float:
        """Atomically increments the fixed-window counter for
        `(tenant_id, resource_class, quota_window_start(now,
        window_seconds))` by `amount` and returns the new total -- a
        single atomic upsert at the repository layer (real
        `INSERT ... ON CONFLICT DO UPDATE` in the SQL implementation),
        so this is correct under concurrent callers, not a
        read-then-write race."""
        ...

    # --- Resource Allocation ---

    async def create_resource_allocation(self, record: ResourceAllocation) -> ResourceAllocation: ...

    async def get_resource_allocation(self, allocation_id: str) -> ResourceAllocation | None: ...

    async def update_resource_allocation(self, record: ResourceAllocation) -> ResourceAllocation: ...

    async def get_active_resource_allocation(self, environment_id: str) -> ResourceAllocation | None:
        """The most recently updated `ACTIVE` allocation for this
        environment -- the baseline `ResourceAllocationService` compares
        a new request against. `None` if this environment has never had
        one approved."""
        ...

    async def list_resource_allocations(
        self, *, environment_id: str | None = None, status: ResourceAllocationStatus | None = None,
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[ResourceAllocation], int]: ...


class AuditabilityClient(Protocol):
    async def emit(self, event: dict[str, Any]) -> None:
        """Best-effort: never the reason a tenancy control-plane write
        fails. Calls Auditability's real `POST /v1/auditability/events`."""
        ...


class TenantScopedListClient(Protocol):
    async def list_tenant_scoped_items(self, *, tenant_id: str) -> list[dict[str, Any]]:
        """Calls this target's own real list endpoint (base_url + list_path
        baked in at construction) with `?tenant_id=<tenant_id>`, and
        returns the raw `items` array. Every module in this platform
        follows the identical `?tenant_id=X` -> `{"items":
        [...each with its own tenant_id...]}` list contract, so this one
        client shape works against any of them with no per-module
        adapter code."""
        ...
