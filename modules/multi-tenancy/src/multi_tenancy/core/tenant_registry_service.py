"""Tenant Registry Service (LLD §2 sub-components, §Level 3 "The tenant
lifecycle state machine"): register/suspend/reactivate/delete, and the
`gate` check other modules' request paths should call before serving a
tenant's request.
"""
from __future__ import annotations

from multi_tenancy.core.domain import (
    InvalidTransitionError,
    TenantGateResult,
    TenantNotFoundError,
    TenantRecord,
    TenantStatus,
    is_legal_transition,
    new_id,
    now,
)
from multi_tenancy.core.ports import MultiTenancyRepository


class TenantRegistryService:
    def __init__(self, repository: MultiTenancyRepository) -> None:
        self._repository = repository

    async def register(self, *, name: str, tier: str = "standard") -> TenantRecord:
        record = TenantRecord(id=new_id(), name=name, tier=tier)
        return await self._repository.create_tenant(record)

    async def get(self, tenant_id: str) -> TenantRecord:
        record = await self._repository.get_tenant(tenant_id)
        if record is None:
            raise TenantNotFoundError(tenant_id)
        return record

    async def list(
        self, *, status: TenantStatus | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[TenantRecord], int]:
        return await self._repository.list_tenants(status=status, limit=limit, offset=offset)

    async def _transition(self, tenant_id: str, to_status: TenantStatus) -> TenantRecord:
        tenant = await self.get(tenant_id)
        if not is_legal_transition(tenant.status, to_status):
            raise InvalidTransitionError(tenant.status, to_status)
        tenant.status = to_status
        tenant.updated_at = now()
        return await self._repository.update_tenant(tenant)

    async def suspend(self, tenant_id: str, *, reason: str) -> TenantRecord:
        # `reason` isn't a stored field on TenantRecord today (LLD keeps the entity
        # lean); it exists as a required argument here specifically so a suspension
        # always has one to log/audit at the call site, the same "an incident-shaped
        # action requires an explanation" posture LLMOps' own rollback already takes.
        return await self._transition(tenant_id, TenantStatus.SUSPENDED)

    async def reactivate(self, tenant_id: str) -> TenantRecord:
        return await self._transition(tenant_id, TenantStatus.ACTIVE)

    async def delete(self, tenant_id: str) -> TenantRecord:
        return await self._transition(tenant_id, TenantStatus.DELETED)

    async def gate(self, tenant_id: str) -> TenantGateResult:
        tenant = await self._repository.get_tenant(tenant_id)
        if tenant is None:
            return TenantGateResult(allowed=False, reason="unknown tenant")
        if tenant.status == TenantStatus.SUSPENDED:
            return TenantGateResult(allowed=False, reason="tenant is suspended")
        if tenant.status == TenantStatus.DELETED:
            return TenantGateResult(allowed=False, reason="tenant is deleted")
        return TenantGateResult(allowed=True, reason="active")
