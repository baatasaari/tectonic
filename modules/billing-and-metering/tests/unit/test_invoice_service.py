"""Tests for core/invoice_service.py -- aggregating metered usage into
invoice lines/total, and the draft -> finalized one-way lifecycle."""
from __future__ import annotations

import pytest

from billing_and_metering.core.domain import (
    InvalidTransitionError,
    InvoiceNotFoundError,
    PricingPlanNotFoundError,
)
from billing_and_metering.core.fakes import StubAuditabilityClient, StubFinOpsClient


async def test_generate_invoice_computes_lines_and_total(harness_factory):
    finops = StubFinOpsClient(total_cost=100.0)
    auditability = StubAuditabilityClient(count=50)
    h = harness_factory(finops=finops, auditability=auditability)
    await h.pricing_plan_service.create(
        tenant_id="acme", name="Standard", unit_prices={"llm.cost_usd": 1.0, "identity-and-access": 0.02},
    )

    generated = await h.invoice_service.generate_invoice(tenant_id="acme", period="monthly")

    assert generated.invoice.status.value == "draft"
    assert generated.invoice.complete is True
    assert generated.invoice.total_amount == pytest.approx(100.0 + 1.0)  # 100*1.0 + 50*0.02
    assert len(generated.lines) == 2


async def test_generate_invoice_raises_when_no_plan_exists(harness):
    with pytest.raises(PricingPlanNotFoundError):
        await harness.invoice_service.generate_invoice(tenant_id="no-plan-tenant", period="monthly")


async def test_generate_invoice_marks_incomplete_when_a_source_is_down(harness_factory):
    finops = StubFinOpsClient(raise_error=True)
    h = harness_factory(finops=finops)
    await h.pricing_plan_service.create(tenant_id="acme", name="Standard", unit_prices={"llm.cost_usd": 1.0})

    generated = await h.invoice_service.generate_invoice(tenant_id="acme", period="monthly")

    assert generated.invoice.complete is False
    assert generated.invoice.total_amount == 0.0
    assert generated.lines == []


async def test_get_invoice_returns_the_invoice_and_its_lines(harness_factory):
    finops = StubFinOpsClient(total_cost=10.0)
    h = harness_factory(finops=finops)
    await h.pricing_plan_service.create(tenant_id="acme", name="Standard", unit_prices={"llm.cost_usd": 1.0})
    generated = await h.invoice_service.generate_invoice(tenant_id="acme", period="monthly")

    fetched = await h.invoice_service.get_invoice(generated.invoice.id)

    assert fetched.invoice.id == generated.invoice.id
    assert len(fetched.lines) == 1


async def test_get_invoice_raises_not_found(harness):
    with pytest.raises(InvoiceNotFoundError):
        await harness.invoice_service.get_invoice("does-not-exist")


async def test_finalize_transitions_draft_to_finalized(harness_factory):
    finops = StubFinOpsClient(total_cost=10.0)
    h = harness_factory(finops=finops)
    await h.pricing_plan_service.create(tenant_id="acme", name="Standard", unit_prices={"llm.cost_usd": 1.0})
    generated = await h.invoice_service.generate_invoice(tenant_id="acme", period="monthly")

    finalized = await h.invoice_service.finalize(generated.invoice.id)

    assert finalized.status.value == "finalized"
    assert finalized.finalized_at is not None


async def test_finalize_is_one_way_cannot_finalize_twice(harness_factory):
    finops = StubFinOpsClient(total_cost=10.0)
    h = harness_factory(finops=finops)
    await h.pricing_plan_service.create(tenant_id="acme", name="Standard", unit_prices={"llm.cost_usd": 1.0})
    generated = await h.invoice_service.generate_invoice(tenant_id="acme", period="monthly")
    await h.invoice_service.finalize(generated.invoice.id)

    with pytest.raises(InvalidTransitionError):
        await h.invoice_service.finalize(generated.invoice.id)


async def test_regenerating_a_draft_invoice_updates_it_in_place_not_a_duplicate(harness_factory):
    finops = StubFinOpsClient(total_cost=10.0)
    h = harness_factory(finops=finops)
    await h.pricing_plan_service.create(tenant_id="acme", name="Standard", unit_prices={"llm.cost_usd": 1.0})

    first = await h.invoice_service.generate_invoice(tenant_id="acme", period="monthly")
    finops.total_cost = 30.0  # usage changed between the two calls
    second = await h.invoice_service.generate_invoice(tenant_id="acme", period="monthly")

    assert second.invoice.id == first.invoice.id
    assert second.invoice.total_amount == pytest.approx(30.0)
    assert len(second.lines) == 1

    _invoices, total = await h.invoice_service.list_invoices(tenant_id="acme")
    assert total == 1


async def test_regenerating_replaces_lines_for_a_resource_no_longer_in_the_plan(harness_factory):
    finops = StubFinOpsClient(total_cost=10.0)
    auditability = StubAuditabilityClient(count=5)
    h = harness_factory(finops=finops, auditability=auditability)
    await h.pricing_plan_service.create(
        tenant_id="acme", name="v1", unit_prices={"llm.cost_usd": 1.0, "identity-and-access": 0.02},
    )
    first = await h.invoice_service.generate_invoice(tenant_id="acme", period="monthly")
    assert len(first.lines) == 2

    # A plan edit drops a resource -- re-metering the same period must not leave its
    # old line behind. list() re-resolves to the tenant's newest plan.
    await h.pricing_plan_service.create(tenant_id="acme", name="v2", unit_prices={"llm.cost_usd": 1.0})
    second = await h.invoice_service.generate_invoice(tenant_id="acme", period="monthly")

    assert second.invoice.id == first.invoice.id
    assert [line.resource for line in second.lines] == ["llm.cost_usd"]


async def test_regenerating_a_finalized_invoice_returns_it_unchanged(harness_factory):
    finops = StubFinOpsClient(total_cost=10.0)
    h = harness_factory(finops=finops)
    await h.pricing_plan_service.create(tenant_id="acme", name="Standard", unit_prices={"llm.cost_usd": 1.0})
    generated = await h.invoice_service.generate_invoice(tenant_id="acme", period="monthly")
    finalized = await h.invoice_service.finalize(generated.invoice.id)

    finops.total_cost = 999.0  # new usage arrives after finalization
    regenerated = await h.invoice_service.generate_invoice(tenant_id="acme", period="monthly")

    assert regenerated.invoice.id == finalized.id
    assert regenerated.invoice.total_amount == pytest.approx(10.0)  # untouched, never re-totaled
    assert finops.calls == [{"tenant_id": "acme", "period": "monthly"}]  # never re-metered either


async def test_list_invoices_filters_by_tenant(harness_factory):
    finops = StubFinOpsClient(total_cost=10.0)
    h = harness_factory(finops=finops)
    await h.pricing_plan_service.create(tenant_id="acme", name="Standard", unit_prices={"llm.cost_usd": 1.0})
    await h.pricing_plan_service.create(tenant_id="other", name="Standard", unit_prices={"llm.cost_usd": 1.0})
    await h.invoice_service.generate_invoice(tenant_id="acme", period="monthly")
    await h.invoice_service.generate_invoice(tenant_id="other", period="monthly")

    results, total = await h.invoice_service.list_invoices(tenant_id="acme")

    assert total == 1
    assert results[0].tenant_id == "acme"
