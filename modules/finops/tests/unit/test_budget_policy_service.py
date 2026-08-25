"""Tests for core/budget_policy_service.py -- create/get."""
from __future__ import annotations

import pytest

from finops.core.domain import BudgetPeriod, BudgetPolicyNotFoundError


async def test_create_persists_and_returns_the_policy(harness):
    policy = await harness.budget_policy_service.create(
        tenant_id="acme", period=BudgetPeriod.MONTHLY, limit_amount=1000.0, alert_threshold_pct=0.75,
    )

    assert policy.tenant_id == "acme"
    assert policy.limit_amount == 1000.0
    assert policy.alert_threshold_pct == 0.75

    fetched = await harness.budget_policy_service.get(policy.id)
    assert fetched.id == policy.id


async def test_get_raises_when_the_policy_does_not_exist(harness):
    with pytest.raises(BudgetPolicyNotFoundError):
        await harness.budget_policy_service.get("does-not-exist")


async def test_create_defaults_alert_threshold_pct(harness):
    policy = await harness.budget_policy_service.create(
        tenant_id="acme", period=BudgetPeriod.DAILY, limit_amount=50.0,
    )

    assert policy.alert_threshold_pct == 0.8
