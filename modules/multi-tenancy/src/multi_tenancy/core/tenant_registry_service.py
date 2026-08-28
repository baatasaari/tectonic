"""Tenant Registry Service (LLD §2 sub-components, §Level 3 "The tenant
lifecycle state machine"): register/suspend/reactivate/delete, the
`gate` check other modules' request paths should call before serving a
tenant's request, and the per-tenant module entitlement set (the
platform's feature-flag store) that gate now also checks.
"""
from __future__ import annotations

from multi_tenancy.core.domain import (
    InvalidTransitionError,
    TenantEntitlementRecord,
    TenantGateResult,
    TenantNotFoundError,
    TenantRecord,
    TenantStatus,
    is_legal_transition,
    new_id,
    now,
)
from multi_tenancy.core.ports import AuditabilityClient, MultiTenancyRepository


class TenantRegistryService:
    def __init__(self, repository: MultiTenancyRepository, auditability: AuditabilityClient) -> None:
        self._repository = repository
        self._auditability = auditability

    async def register(
        self, *, name: str, tier: str = "standard", organisation_id: str | None = None,
    ) -> TenantRecord:
        record = TenantRecord(id=new_id(), name=name, tier=tier, organisation_id=organisation_id)
        created = await self._repository.create_tenant(record)
        await self._auditability.emit({
            "event": "tenant_created", "tenant_id": created.id, "name": created.name,
            "organisation_id": organisation_id,
        })
        return created

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
        from_status = tenant.status
        tenant.status = to_status
        tenant.updated_at = now()
        updated = await self._repository.update_tenant(tenant)
        await self._auditability.emit({
            "event": "tenant_status_changed", "tenant_id": tenant_id,
            "from_status": from_status.value, "to_status": to_status.value,
        })
        return updated

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

    async def gate(self, tenant_id: str, *, module: str | None = None) -> TenantGateResult:
        """The one real integration point every other module's request
        path is meant to call before serving a request. Two independent
        checks, in order:

        1. Tenant status -- unknown/suspended/deleted always denies,
           regardless of `module`.
        2. Entitlement (feature flag), only when `module` is given AND
           this tenant's `entitlements_configured_at` is set. A tenant
           that has never had its entitlements explicitly configured is
           treated as ungated -- not yet migrated onto the subscription
           model, or a platform-internal tenant -- and allowed through;
           this is a deliberate rollout-safety default, not an
           oversight: shipping this check must never silently start
           denying every tenant that predates it. The instant a tenant
           HAS been configured -- even with an explicit empty module
           set, meaning "this plan includes zero modules" -- the check
           becomes real, and an unlisted module is denied.
        """
        tenant = await self._repository.get_tenant(tenant_id)
        if tenant is None:
            return TenantGateResult(allowed=False, reason="unknown tenant")
        if tenant.status == TenantStatus.SUSPENDED:
            return TenantGateResult(allowed=False, reason="tenant is suspended")
        if tenant.status == TenantStatus.DELETED:
            return TenantGateResult(allowed=False, reason="tenant is deleted")

        if module is not None and tenant.entitlements_configured_at is not None:
            entitled = await self._repository.list_entitlements(tenant_id)
            if module not in {e.module_name for e in entitled}:
                return TenantGateResult(allowed=False, reason=f"module not included in subscription: {module}")

        return TenantGateResult(allowed=True, reason="active")

    async def set_entitlements(self, tenant_id: str, *, module_names: list[str]) -> list[TenantEntitlementRecord]:
        await self.get(tenant_id)  # raises TenantNotFoundError for an unknown tenant
        return await self._repository.replace_entitlements(tenant_id=tenant_id, module_names=module_names)

    async def list_entitlements(self, tenant_id: str) -> list[TenantEntitlementRecord]:
        await self.get(tenant_id)
        return await self._repository.list_entitlements(tenant_id)
