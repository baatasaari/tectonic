"""In-memory fakes for unit tests (LLD "Deployability and testability
contract")."""
from __future__ import annotations

from typing import Any

from multi_tenancy.core.domain import (
    IsolationProbeResult,
    TenantEntitlementRecord,
    TenantRecord,
    TenantStatus,
    now,
)

_UNSET = object()


class InMemoryMultiTenancyRepository:
    def __init__(self) -> None:
        self.tenants: dict[str, TenantRecord] = {}
        self.probe_results: list[IsolationProbeResult] = []
        self.entitlements: dict[str, list[TenantEntitlementRecord]] = {}

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


__all__ = ["InMemoryMultiTenancyRepository", "StubTenantScopedListClient"]
