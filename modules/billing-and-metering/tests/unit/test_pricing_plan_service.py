"""Tests for core/pricing_plan_service.py -- create/get/list, and
resolving the plan that actually applies to a tenant."""
from __future__ import annotations

import pytest

from billing_and_metering.core.domain import PricingPlanNotFoundError


async def test_create_and_get_plan(harness):
    plan = await harness.pricing_plan_service.create(
        tenant_id="acme", name="Standard", unit_prices={"llm.cost_usd": 1.0},
    )

    fetched = await harness.pricing_plan_service.get(plan.id)

    assert fetched.id == plan.id
    assert fetched.unit_prices == {"llm.cost_usd": 1.0}


async def test_resolve_active_plan_prefers_the_tenants_own_plan(harness):
    await harness.pricing_plan_service.create(tenant_id=None, name="Default", unit_prices={"llm.cost_usd": 1.0})
    tenant_plan = await harness.pricing_plan_service.create(
        tenant_id="acme", name="Acme Custom", unit_prices={"llm.cost_usd": 0.5},
    )

    resolved = await harness.pricing_plan_service.resolve_active_plan("acme")

    assert resolved.id == tenant_plan.id


async def test_resolve_active_plan_falls_back_to_the_global_default(harness):
    default_plan = await harness.pricing_plan_service.create(
        tenant_id=None, name="Default", unit_prices={"llm.cost_usd": 1.0},
    )

    resolved = await harness.pricing_plan_service.resolve_active_plan("no-plan-tenant")

    assert resolved.id == default_plan.id


async def test_resolve_active_plan_raises_when_neither_exists(harness):
    with pytest.raises(PricingPlanNotFoundError):
        await harness.pricing_plan_service.resolve_active_plan("no-plan-tenant")


async def test_list_plans_filters_by_tenant(harness):
    await harness.pricing_plan_service.create(tenant_id="acme", name="A", unit_prices={})
    await harness.pricing_plan_service.create(tenant_id="other", name="B", unit_prices={})

    results, total = await harness.pricing_plan_service.list(tenant_id="acme")

    assert total == 1
    assert results[0].name == "A"
