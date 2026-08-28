"""In-memory fakes for unit tests (LLD "Deployability and testability
contract")."""
from __future__ import annotations

from typing import Any

from multi_tenancy.core.domain import (
    EnvironmentRecord,
    HierarchyStatus,
    IsolationProbeResult,
    OrganisationRecord,
    TenantEntitlementRecord,
    TenantRecord,
    TenantStatus,
    WorkspaceRecord,
    now,
)

_UNSET = object()


class InMemoryMultiTenancyRepository:
    def __init__(self) -> None:
        self.tenants: dict[str, TenantRecord] = {}
        self.probe_results: list[IsolationProbeResult] = []
        self.entitlements: dict[str, list[TenantEntitlementRecord]] = {}
        self.organisations: dict[str, OrganisationRecord] = {}
        self.workspaces: dict[str, WorkspaceRecord] = {}
        self.environments: dict[str, EnvironmentRecord] = {}

    async def create_tenant(self, record: TenantRecord) -> TenantRecord:
        self.tenants[record.id] = record
        return record

    async def get_tenant(self, tenant_id: str) -> TenantRecord | None:
        return self.tenants.get(tenant_id)

    async def update_tenant(self, record: TenantRecord) -> TenantRecord:
        self.tenants[record.id] = record
        return record

    async def replace_entitlements(
        self, *, tenant_id: str, module_names: list[str],
    ) -> list[TenantEntitlementRecord]:
        records = [TenantEntitlementRecord(tenant_id=tenant_id, module_name=name) for name in module_names]
        self.entitlements[tenant_id] = records
        tenant = self.tenants.get(tenant_id)
        if tenant is not None:
            tenant.entitlements_configured_at = now()
        return records

    async def list_entitlements(self, tenant_id: str) -> list[TenantEntitlementRecord]:
        return list(self.entitlements.get(tenant_id, []))

    async def list_tenants(
        self, *, status: TenantStatus | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[TenantRecord], int]:
        results = list(self.tenants.values())
        if status is not None:
            results = [t for t in results if t.status == status]
        results = sorted(results, key=lambda t: t.created_at)
        return results[offset:offset + limit], len(results)

    async def create_probe_result(self, record: IsolationProbeResult) -> IsolationProbeResult:
        self.probe_results.append(record)
        return record

    async def list_probe_results(
        self, *, tenant_id: str | None = None, target_name: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[IsolationProbeResult], int]:
        results = list(self.probe_results)
        if tenant_id is not None:
            results = [r for r in results if r.tenant_id == tenant_id]
        if target_name is not None:
            results = [r for r in results if r.target_name == target_name]
        results = sorted(results, key=lambda r: r.checked_at, reverse=True)
        return results[offset:offset + limit], len(results)

    # --- Organisation / Workspace / Environment ---

    async def create_organisation(self, record: OrganisationRecord) -> OrganisationRecord:
        self.organisations[record.id] = record
        return record

    async def get_organisation(self, organisation_id: str) -> OrganisationRecord | None:
        return self.organisations.get(organisation_id)

    async def update_organisation(self, record: OrganisationRecord) -> OrganisationRecord:
        self.organisations[record.id] = record
        return record

    async def list_organisations(
        self, *, status: HierarchyStatus | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[OrganisationRecord], int]:
        results = list(self.organisations.values())
        if status is not None:
            results = [o for o in results if o.status == status]
        results = sorted(results, key=lambda o: o.created_at)
        return results[offset:offset + limit], len(results)

    async def create_workspace(self, record: WorkspaceRecord) -> WorkspaceRecord:
        self.workspaces[record.id] = record
        return record

    async def get_workspace(self, workspace_id: str) -> WorkspaceRecord | None:
        return self.workspaces.get(workspace_id)

    async def update_workspace(self, record: WorkspaceRecord) -> WorkspaceRecord:
        self.workspaces[record.id] = record
        return record

    async def list_workspaces(
        self, *, tenant_id: str | None = None, status: HierarchyStatus | None = None,
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[WorkspaceRecord], int]:
        results = list(self.workspaces.values())
        if tenant_id is not None:
            results = [w for w in results if w.tenant_id == tenant_id]
        if status is not None:
            results = [w for w in results if w.status == status]
        results = sorted(results, key=lambda w: w.created_at)
        return results[offset:offset + limit], len(results)

    async def create_environment(self, record: EnvironmentRecord) -> EnvironmentRecord:
        self.environments[record.id] = record
        return record

    async def get_environment(self, environment_id: str) -> EnvironmentRecord | None:
        return self.environments.get(environment_id)

    async def update_environment(self, record: EnvironmentRecord) -> EnvironmentRecord:
        self.environments[record.id] = record
        return record

    async def list_environments(
        self, *, workspace_id: str | None = None, status: HierarchyStatus | None = None,
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[EnvironmentRecord], int]:
        results = list(self.environments.values())
        if workspace_id is not None:
            results = [e for e in results if e.workspace_id == workspace_id]
        if status is not None:
            results = [e for e in results if e.status == status]
        results = sorted(results, key=lambda e: e.created_at)
        return results[offset:offset + limit], len(results)


class StubAuditabilityClient:
    """Records every emitted event and never raises -- mirrors
    `HTTPAuditabilityClient.emit`'s own best-effort contract, so a
    caller test never needs a try/except around it."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def emit(self, event: dict[str, Any]) -> None:
        self.events.append(event)


class StubTenantScopedListClient:
    """`items` is the raw list this stub returns as-is -- pass items whose
    own `tenant_id` deliberately doesn't match the probed tenant to
    exercise the breach-detection path. `raise_error=True` simulates an
    unreachable target."""

    def __init__(self, *, items: list[dict[str, Any]] | object = _UNSET, raise_error: bool = False) -> None:
        self.calls: list[dict] = []
        self._items = [] if items is _UNSET else items
        self._raise_error = raise_error

    async def list_tenant_scoped_items(self, *, tenant_id: str) -> list[dict[str, Any]]:
        self.calls.append({"tenant_id": tenant_id})
        if self._raise_error:
            raise RuntimeError("target is down")
        return self._items


__all__ = ["InMemoryMultiTenancyRepository", "StubAuditabilityClient", "StubTenantScopedListClient"]
