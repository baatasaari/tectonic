"""Tests for core/usage_aggregation_service.py -- combining LLM Gateway's
live spend with locally-ingested usage events into one CostReport, and the
utilisation_ratio/alert computation against a budget policy."""
from __future__ import annotations

from datetime import UTC, datetime

from finops.core.domain import BudgetPeriod, BudgetPolicyRecord, UsageEventRecord
from finops.core.fakes import StubLLMGatewaySpendClient


async def test_cost_report_sums_llm_gateway_spend_and_local_usage_events(harness_factory):
    h = harness_factory(llm_gateway=StubLLMGatewaySpendClient(spend=40.0))
    await h.repository.create_usage_event(
        UsageEventRecord(
            id="e1", tenant_id="acme", source_module="vector-db", resource_type="storage-gb",
            quantity=10, unit_cost=1.5, cost=15.0, occurred_at=datetime.now(UTC),
        )
    )

    report = await h.usage_aggregation_service.cost_report(tenant_id="acme", period=BudgetPeriod.MONTHLY)

    assert report.llm_gateway_spend == 40.0
    assert report.other_usage_cost == 15.0
    assert report.total_cost == 55.0


async def test_cost_report_excludes_usage_events_outside_the_current_period(harness):
    await harness.repository.create_usage_event(
        UsageEventRecord(
            id="e1", tenant_id="acme", source_module="vector-db", resource_type="storage-gb",
            quantity=10, unit_cost=1.0, cost=10.0, occurred_at=datetime(2020, 1, 1, tzinfo=UTC),
        )
    )

    report = await harness.usage_aggregation_service.cost_report(tenant_id="acme", period=BudgetPeriod.MONTHLY)

    assert report.other_usage_cost == 0.0


async def test_cost_report_without_a_budget_policy_has_no_utilisation_or_alert(harness):
    report = await harness.usage_aggregation_service.cost_report(tenant_id="acme", period=BudgetPeriod.MONTHLY)

    assert report.utilisation_ratio is None
    assert report.alert is False


async def test_cost_report_computes_utilisation_ratio_against_a_budget_policy(harness_factory):
    h = harness_factory(llm_gateway=StubLLMGatewaySpendClient(spend=80.0))
    policy = BudgetPolicyRecord(
        id="p1", tenant_id="acme", period=BudgetPeriod.MONTHLY, limit_amount=100.0, alert_threshold_pct=0.8,
    )

    report = await h.usage_aggregation_service.cost_report(tenant_id="acme", period=BudgetPeriod.MONTHLY, budget_policy=policy)

    assert report.utilisation_ratio == 0.8
    assert report.alert is True


async def test_cost_report_alert_is_false_below_the_threshold(harness_factory):
    h = harness_factory(llm_gateway=StubLLMGatewaySpendClient(spend=10.0))
    policy = BudgetPolicyRecord(
        id="p1", tenant_id="acme", period=BudgetPeriod.MONTHLY, limit_amount=100.0, alert_threshold_pct=0.8,
    )

    report = await h.usage_aggregation_service.cost_report(tenant_id="acme", period=BudgetPeriod.MONTHLY, budget_policy=policy)

    assert report.utilisation_ratio == 0.1
    assert report.alert is False
