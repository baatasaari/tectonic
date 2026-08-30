"""Isolation Probe Service (LLD §2 sub-components, §Level 3 "The
isolation probe"): calls a registered target's real list endpoint
scoped to one tenant and flags any returned item whose own `tenant_id`
doesn't match as a breach. Fails closed: a target that can't be reached
is recorded as `passed=False`, never a silent assumed-pass -- isolation
is only ever reported verified when it was actually checked.
"""
from __future__ import annotations

from collections.abc import Awaitable
from typing import TypeVar

from multi_tenancy.core.domain import IsolationProbeResult, ProbeTargetNotFoundError, new_id
from multi_tenancy.core.ports import MultiTenancyRepository, TenantScopedListClient
from multi_tenancy.telemetry.logging import get_logger
from multi_tenancy.telemetry.metrics import (
    multi_tenancy_isolation_breach_incidents_total,
    multi_tenancy_isolation_probes_total,
)

logger = get_logger(component="isolation_probe_service")

T = TypeVar("T")


class IsolationProbeService:
    def __init__(self, repository: MultiTenancyRepository, clients: dict[str, TenantScopedListClient]) -> None:
        self._repository = repository
        self._clients = clients

    @staticmethod
    async def _safe_call(call: Awaitable[T], *, default: T) -> T:
        try:
            return await call
        except Exception as exc:
            logger.warning("isolation_probe_target_unavailable", error=str(exc))
            return default

    async def run_probe(self, *, tenant_id: str, target_name: str) -> IsolationProbeResult:
        client = self._clients.get(target_name)
        if client is None:
            raise ProbeTargetNotFoundError(target_name)

        items = await self._safe_call(client.list_tenant_scoped_items(tenant_id=tenant_id), default=None)

        if items is None:
            result = IsolationProbeResult(
                id=new_id(), tenant_id=tenant_id, target_name=target_name, passed=False, breach_count=0,
                sample_size=0, details=f"probe_unavailable: {target_name} unreachable",
            )
        else:
            foreign = [item for item in items if item.get("tenant_id") != tenant_id]
            passed = len(foreign) == 0
            result = IsolationProbeResult(
                id=new_id(), tenant_id=tenant_id, target_name=target_name, passed=passed,
                breach_count=len(foreign), sample_size=len(items),
                details="ok" if passed else f"{len(foreign)} foreign record(s) returned for a tenant-scoped query",
            )
            if not passed:
                multi_tenancy_isolation_breach_incidents_total.labels(target_name=target_name).inc(len(foreign))
                logger.error(
                    "isolation_breach_detected", tenant_id=tenant_id, target_name=target_name,
                    breach_count=len(foreign),
                )

        multi_tenancy_isolation_probes_total.labels(target_name=target_name, passed=str(result.passed)).inc()
        return await self._repository.create_probe_result(result)
