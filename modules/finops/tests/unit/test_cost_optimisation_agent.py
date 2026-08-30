"""Tests for core/cost_optimisation_agent.py -- the one bounded autonomous
action this module takes: lowering a budget policy's alert_threshold_pct,
one configured step at a time, never below a configured floor, and only
when a forecast actually projects a breach."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

from finops.core.domain import BudgetPeriod, BudgetPolicyRecord
from finops.core.fakes import StubLLMGatewaySpendClient


def _mid_period():
    # Comfortably past the 5% forecast floor for a monthly period.
    return patch("finops.core.forecasting_service.now", return_value=datetime(2026, 1, 16, tzinfo=UTC))


async def test_no_action_when_forecast_is_insufficient_data(harness_factory):
    h = harness_factory(llm_gateway=StubLLMGatewaySpendClient(spend=10.0))
    policy = BudgetPolicyRecord(id="p1", tenant_id="acme", period=BudgetPeriod.MONTHLY, limit_amount=100.0)
    with patch("finops.core.forecasting_service.now", return_value=datetime(2026, 1, 1, 0, 30, tzinfo=UTC)):
        action = await h.cost_optimisation_agent.evaluate(policy)

    assert action is None


async def test_no_action_when_forecast_is_within_budget(harness_factory):
    h = harness_factory(llm_gateway=StubLLMGatewaySpendClient(spend=5.0))
    policy = BudgetPolicyRecord(id="p1", tenant_id="acme", period=BudgetPeriod.MONTHLY, limit_amount=1000.0)
    with _mid_period():
        action = await h.cost_optimisation_agent.evaluate(policy)

    assert action is None


async def test_lowers_alert_threshold_when_forecast_projects_a_breach(harness_factory):
    h = harness_factory(llm_gateway=StubLLMGatewaySpendClient(spend=80.0), alert_threshold_step=0.05, min_alert_threshold_pct=0.5)
    policy = BudgetPolicyRecord(id="p1", tenant_id="acme", period=BudgetPeriod.MONTHLY, limit_amount=100.0, alert_threshold_pct=0.8)
    await h.repository.create_budget_policy(policy)

    with _mid_period():
        action = await h.cost_optimisation_agent.evaluate(policy)

    assert action is not None
    assert action.action_type == "lowered_alert_threshold"
    assert action.previous_value == 0.8
    assert action.new_value == 0.75
    assert policy.alert_threshold_pct == 0.75

    actions, total = await h.repository.list_optimisation_actions(budget_policy_id="p1")
    assert total == 1
    assert actions[0].id == action.id


async def test_never_lowers_the_threshold_below_the_configured_floor(harness_factory):
    h = harness_factory(llm_gateway=StubLLMGatewaySpendClient(spend=80.0), min_alert_threshold_pct=0.5)
    policy = BudgetPolicyRecord(id="p1", tenant_id="acme", period=BudgetPeriod.MONTHLY, limit_amount=100.0, alert_threshold_pct=0.5)
    await h.repository.create_budget_policy(policy)

    with _mid_period():
        action = await h.cost_optimisation_agent.evaluate(policy)

    assert action is None
    assert policy.alert_threshold_pct == 0.5


async def test_new_value_is_clamped_at_the_floor_even_when_a_step_would_overshoot_it(harness_factory):
    h = harness_factory(llm_gateway=StubLLMGatewaySpendClient(spend=80.0), alert_threshold_step=0.10, min_alert_threshold_pct=0.5)
    policy = BudgetPolicyRecord(id="p1", tenant_id="acme", period=BudgetPeriod.MONTHLY, limit_amount=100.0, alert_threshold_pct=0.55)
    await h.repository.create_budget_policy(policy)

    with _mid_period():
        action = await h.cost_optimisation_agent.evaluate(policy)

    assert action is not None
    assert action.new_value == 0.5


async def test_action_reason_mentions_forecast_and_limit(harness_factory):
    h = harness_factory(llm_gateway=StubLLMGatewaySpendClient(spend=80.0))
    policy = BudgetPolicyRecord(id="p1", tenant_id="acme", period=BudgetPeriod.MONTHLY, limit_amount=100.0, alert_threshold_pct=0.8)
    await h.repository.create_budget_policy(policy)

    with _mid_period():
        action = await h.cost_optimisation_agent.evaluate(policy)

    assert "forecast" in action.reason
    assert "100.00" in action.reason
