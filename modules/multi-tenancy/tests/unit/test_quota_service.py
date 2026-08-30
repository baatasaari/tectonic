"""Tests for core/quota_service.py -- QuotaSetService (wholesale-replace
limits) and QuotaEnforcementService (real rate-window counters for
`_per_minute`/etc. resource classes, stateless ceiling checks for
everything else).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest


async def test_get_returns_none_before_any_limits_are_set(harness):
    quota_set = await harness.quota_set_service.get("acme")
    assert quota_set is None


async def test_set_limits_stores_and_stamps_configured_at(harness):
    quota_set = await harness.quota_set_service.set_limits(
        "acme", limits={"requests_per_minute": 600, "storage_gb": 500},
    )

    assert quota_set.configured_at is not None
    assert quota_set.limits == {"requests_per_minute": 600, "storage_gb": 500}
    assert quota_set.version == 1

    fetched = await harness.quota_set_service.get("acme")
    assert fetched.limits == {"requests_per_minute": 600, "storage_gb": 500}


async def test_set_limits_is_a_wholesale_replace_not_a_patch(harness):
    await harness.quota_set_service.set_limits("acme", limits={"requests_per_minute": 600, "storage_gb": 500})

    replaced = await harness.quota_set_service.set_limits("acme", limits={"requests_per_minute": 1200})

    assert replaced.limits == {"requests_per_minute": 1200}
    assert replaced.version == 2


async def test_check_and_consume_allows_everything_for_an_unconfigured_tenant(harness):
    result = await harness.quota_enforcement_service.check_and_consume(
        "acme", resource_class="requests_per_minute", amount=1_000_000,
    )

    assert result.allowed is True
    assert result.limit is None
    assert result.reason == "no quota configured for this resource class"


async def test_rate_shaped_resource_class_is_enforced_within_the_window(harness):
    await harness.quota_set_service.set_limits("acme", limits={"requests_per_minute": 5})
    at = datetime(2026, 1, 1, tzinfo=UTC)

    for _ in range(5):
        result = await harness.quota_enforcement_service.check_and_consume(
            "acme", resource_class="requests_per_minute", amount=1, at=at,
        )
        assert result.allowed is True

    sixth = await harness.quota_enforcement_service.check_and_consume(
        "acme", resource_class="requests_per_minute", amount=1, at=at,
    )
    assert sixth.allowed is False
    assert sixth.used == 6
    assert sixth.remaining == 0.0
    assert "requests_per_minute" in sixth.reason


async def test_a_new_window_resets_the_counter(harness):
    await harness.quota_set_service.set_limits("acme", limits={"requests_per_minute": 2})
    first_window = datetime(2026, 1, 1, 0, 0, 30, tzinfo=UTC)
    next_window = first_window + timedelta(minutes=1)

    await harness.quota_enforcement_service.check_and_consume(
        "acme", resource_class="requests_per_minute", amount=2, at=first_window,
    )
    denied = await harness.quota_enforcement_service.check_and_consume(
        "acme", resource_class="requests_per_minute", amount=1, at=first_window,
    )
    assert denied.allowed is False

    allowed_in_new_window = await harness.quota_enforcement_service.check_and_consume(
        "acme", resource_class="requests_per_minute", amount=1, at=next_window,
    )
    assert allowed_in_new_window.allowed is True
    assert allowed_in_new_window.used == 1


async def test_different_tenants_have_independent_counters(harness):
    await harness.quota_set_service.set_limits("acme", limits={"requests_per_minute": 1})
    await harness.quota_set_service.set_limits("globex", limits={"requests_per_minute": 1})
    at = datetime(2026, 1, 1, tzinfo=UTC)

    acme_result = await harness.quota_enforcement_service.check_and_consume(
        "acme", resource_class="requests_per_minute", at=at,
    )
    globex_result = await harness.quota_enforcement_service.check_and_consume(
        "globex", resource_class="requests_per_minute", at=at,
    )

    assert acme_result.allowed is True
    assert globex_result.allowed is True


async def test_capacity_shaped_resource_class_checks_caller_reported_usage(harness):
    await harness.quota_set_service.set_limits("acme", limits={"storage_gb": 500})

    within = await harness.quota_enforcement_service.check_and_consume(
        "acme", resource_class="storage_gb", amount=50, current_usage=400,
    )
    assert within.allowed is True
    assert within.used == 450

    over = await harness.quota_enforcement_service.check_and_consume(
        "acme", resource_class="storage_gb", amount=200, current_usage=400,
    )
    assert over.allowed is False


async def test_capacity_shaped_resource_class_requires_current_usage(harness):
    await harness.quota_set_service.set_limits("acme", limits={"storage_gb": 500})

    with pytest.raises(ValueError, match="current_usage"):
        await harness.quota_enforcement_service.check_and_consume("acme", resource_class="storage_gb", amount=50)
