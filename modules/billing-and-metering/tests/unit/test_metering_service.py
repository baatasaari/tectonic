"""Tests for core/metering_service.py -- meters a plan's resources
from real FinOps/Auditability signals, and never fabricates zero usage
when a source is unreachable."""
from __future__ import annotations

from billing_and_metering.core.domain import PricingPlanRecord, new_id
from billing_and_metering.core.fakes import (
    StubAuditabilityClient,
    StubFinOpsClient,
    StubMultiTenancyClient,
)
from billing_and_metering.core.metering_service import MeteringService


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


async def test_re_metering_the_same_period_upserts_not_duplicates(harness_factory):
    # The idempotent ledger's own point: a retried/re-triggered metering run for a
    # period already metered must never leave a second row behind to double-count.
    finops = StubFinOpsClient(total_cost=10.0)
    h = harness_factory(finops=finops)
    plan = _plan(**{"llm.cost_usd": 1.0})

    await h.metering_service.meter_tenant(tenant_id="acme", period="monthly", plan=plan)
    finops.total_cost = 25.0  # usage changed between runs -- the upsert must reflect that
    records, complete = await h.metering_service.meter_tenant(tenant_id="acme", period="monthly", plan=plan)

    assert complete is True
    assert records[0].quantity == 25.0
    _all_records, total = await h.repository.list_usage_records(tenant_id="acme")
    assert total == 1


async def test_a_resource_the_tenant_is_not_entitled_to_is_skipped_and_not_billed(harness_factory):
    multi_tenancy = StubMultiTenancyClient(denied_modules={"identity-and-access"})
    auditability = StubAuditabilityClient(count=17)
    h = harness_factory(auditability=auditability, multi_tenancy=multi_tenancy)
    plan = _plan(**{"identity-and-access": 0.01})

    records, complete = await h.metering_service.meter_tenant(tenant_id="acme", period="monthly", plan=plan)

    # A denied entitlement is a deliberate exclusion, not missing data -- it must never
    # mark the invoice incomplete the way an unreachable source does.
    assert complete is True
    assert records == []


async def test_llm_cost_is_gated_against_the_llm_gateway_module_name(harness_factory):
    multi_tenancy = StubMultiTenancyClient(denied_modules={"llm-gateway"})
    finops = StubFinOpsClient(total_cost=42.5)
    h = harness_factory(finops=finops, multi_tenancy=multi_tenancy)
    plan = _plan(**{"llm.cost_usd": 1.0})

    records, complete = await h.metering_service.meter_tenant(tenant_id="acme", period="monthly", plan=plan)

    assert complete is True
    assert records == []
    assert multi_tenancy.gate_calls == [{"tenant_id": "acme", "module": "llm-gateway"}]


async def test_an_entitled_resource_is_still_metered_normally(harness_factory):
    multi_tenancy = StubMultiTenancyClient(denied_modules={"some-other-module"})
    auditability = StubAuditabilityClient(count=17)
    h = harness_factory(auditability=auditability, multi_tenancy=multi_tenancy)
    plan = _plan(**{"identity-and-access": 0.01})

    records, complete = await h.metering_service.meter_tenant(tenant_id="acme", period="monthly", plan=plan)

    assert complete is True
    assert len(records) == 1
    assert records[0].resource == "identity-and-access"


async def test_no_multi_tenancy_client_configured_meters_everything(harness_factory):
    # multi_tenancy=None -- the same fail-open answer an unreachable one gives, just
    # via absence rather than an error.
    auditability = StubAuditabilityClient(count=17)
    repository = harness_factory().repository
    service = MeteringService(repository, StubFinOpsClient(), auditability, None)
    plan = _plan(**{"identity-and-access": 0.01})

    records, complete = await service.meter_tenant(tenant_id="acme", period="monthly", plan=plan)

    assert complete is True
    assert len(records) == 1
