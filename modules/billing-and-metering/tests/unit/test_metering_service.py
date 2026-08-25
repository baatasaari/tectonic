"""Tests for core/metering_service.py -- meters a plan's resources
from real FinOps/Auditability signals, and never fabricates zero usage
when a source is unreachable."""
from __future__ import annotations

from billing_and_metering.core.domain import PricingPlanRecord, new_id
from billing_and_metering.core.fakes import StubAuditabilityClient, StubFinOpsClient


def _plan(**unit_prices) -> PricingPlanRecord:
    return PricingPlanRecord(id=new_id(), tenant_id="acme", name="test", unit_prices=unit_prices)


async def test_meters_llm_cost_from_finops(harness_factory):
    finops = StubFinOpsClient(total_cost=42.5)
    h = harness_factory(finops=finops)
    plan = _plan(**{"llm.cost_usd": 1.0})

    records, complete = await h.metering_service.meter_tenant(tenant_id="acme", period="monthly", plan=plan)

    assert complete is True
    assert len(records) == 1
    assert records[0].resource == "llm.cost_usd"
    assert records[0].quantity == 42.5
    assert records[0].source == "finops"


async def test_meters_other_resources_as_auditability_event_counts(harness_factory):
    auditability = StubAuditabilityClient(count=17)
    h = harness_factory(auditability=auditability)
    plan = _plan(**{"secrets-and-credential-management": 0.01})

    records, complete = await h.metering_service.meter_tenant(tenant_id="acme", period="monthly", plan=plan)

    assert complete is True
    assert records[0].resource == "secrets-and-credential-management"
    assert records[0].quantity == 17
    assert records[0].source == "auditability"


async def test_a_down_finops_skips_that_resource_and_marks_incomplete(harness_factory):
    finops = StubFinOpsClient(raise_error=True)
    h = harness_factory(finops=finops)
    plan = _plan(**{"llm.cost_usd": 1.0})

    records, complete = await h.metering_service.meter_tenant(tenant_id="acme", period="monthly", plan=plan)

    assert complete is False
    assert records == []


async def test_a_down_auditability_skips_that_resource_and_marks_incomplete(harness_factory):
    auditability = StubAuditabilityClient(raise_error=True)
    h = harness_factory(auditability=auditability)
    plan = _plan(**{"identity-and-access": 0.01})

    records, complete = await h.metering_service.meter_tenant(tenant_id="acme", period="monthly", plan=plan)

    assert complete is False
    assert records == []


async def test_one_down_source_does_not_block_metering_the_rest(harness_factory):
    finops = StubFinOpsClient(raise_error=True)
    auditability = StubAuditabilityClient(count=5)
    h = harness_factory(finops=finops, auditability=auditability)
    plan = _plan(**{"llm.cost_usd": 1.0, "identity-and-access": 0.01})

    records, complete = await h.metering_service.meter_tenant(tenant_id="acme", period="monthly", plan=plan)

    assert complete is False
    assert len(records) == 1
    assert records[0].resource == "identity-and-access"


async def test_usage_records_are_persisted(harness_factory):
    finops = StubFinOpsClient(total_cost=10.0)
    h = harness_factory(finops=finops)
    plan = _plan(**{"llm.cost_usd": 1.0})

    await h.metering_service.meter_tenant(tenant_id="acme", period="monthly", plan=plan)

    _records, total = await h.repository.list_usage_records(tenant_id="acme")
    assert total == 1
