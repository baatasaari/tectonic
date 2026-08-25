"""Abstract ports this module depends on: persistence, and the one
generic client shape the Isolation Probe Service reuses against every
registered platform module.
"""
from __future__ import annotations

from typing import Any, Protocol

from multi_tenancy.core.domain import IsolationProbeResult, TenantRecord, TenantStatus


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
