"""Pricing Plan Service (LLD §2 sub-components): create/get/list plans,
resolve the one plan that actually applies to a tenant, and sync a
tenant-specific plan's module list to Multi-tenancy's feature-flag
store so the rest of the platform's entitlement gate reflects what the
tenant is actually paying for.
"""
from __future__ import annotations

from billing_and_metering.core.domain import (
    LLM_COST_RESOURCE,
    PricingPlanNotFoundError,
    PricingPlanRecord,
    new_id,
)
from billing_and_metering.core.ports import BillingRepository, MultiTenancyClient


class PricingPlanService:
    def __init__(self, repository: BillingRepository, multi_tenancy: MultiTenancyClient | None = None) -> None:
        self._repository = repository
        self._multi_tenancy = multi_tenancy

    async def create(
        self, *, tenant_id: str | None, name: str, unit_prices: dict[str, float],
    ) -> PricingPlanRecord:
        plan = PricingPlanRecord(id=new_id(), tenant_id=tenant_id, name=name, unit_prices=unit_prices)
        created = await self._repository.create_pricing_plan(plan)

        # Only a tenant-specific plan (not the global default, which isn't any one
        # tenant's entitlement set) syncs to Multi-tenancy. `"llm.cost_usd"` is a
        # metered resource, not a module, so it's never itself an entitlement.
        if created.tenant_id is not None and self._multi_tenancy is not None:
            module_names = [key for key in created.unit_prices if key != LLM_COST_RESOURCE]
            await self._multi_tenancy.sync_entitlements(tenant_id=created.tenant_id, module_names=module_names)

        return created

    async def get(self, plan_id: str) -> PricingPlanRecord | None:
        return await self._repository.get_pricing_plan(plan_id)

    async def list(
        self, *, tenant_id: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[PricingPlanRecord], int]:
        return await self._repository.list_pricing_plans(tenant_id=tenant_id, limit=limit, offset=offset)

    async def resolve_active_plan(self, tenant_id: str) -> PricingPlanRecord:
        """The plan `MeteringService` actually meters against: the
        tenant's own plan if it has one, else the global default --
        never a fabricated empty plan."""
        plan = await self._repository.get_pricing_plan_for_tenant(tenant_id)
        if plan is not None:
            return plan
        default_plan = await self._repository.get_default_pricing_plan()
        if default_plan is not None:
            return default_plan
        raise PricingPlanNotFoundError(tenant_id)
