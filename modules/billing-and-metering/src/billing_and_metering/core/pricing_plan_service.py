"""Pricing Plan Service (LLD §2 sub-components): create/get/list plans,
and resolve the one plan that actually applies to a tenant.
"""
from __future__ import annotations

from billing_and_metering.core.domain import PricingPlanNotFoundError, PricingPlanRecord, new_id
from billing_and_metering.core.ports import BillingRepository


class PricingPlanService:
    def __init__(self, repository: BillingRepository) -> None:
        self._repository = repository

    async def create(
        self, *, tenant_id: str | None, name: str, unit_prices: dict[str, float],
    ) -> PricingPlanRecord:
        plan = PricingPlanRecord(id=new_id(), tenant_id=tenant_id, name=name, unit_prices=unit_prices)
        return await self._repository.create_pricing_plan(plan)

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
