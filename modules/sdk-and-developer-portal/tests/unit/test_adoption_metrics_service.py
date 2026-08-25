"""Tests for core/adoption_metrics_service.py -- time-to-first-call
computed from real Auditability history, and the portal-wide adoption
rate. Insufficient data returns `None`, never a fabricated zero."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from sdk_and_developer_portal.core.domain import DeveloperNotFoundError


async def test_time_to_first_call_is_none_with_no_activity(harness):
    developer = await harness.developer_service.register(name="Ada", email="ada@example.com")

    metrics = await harness.adoption_service.time_to_first_call(developer.id)

    assert metrics.first_call_at is None
    assert metrics.time_to_first_call_seconds is None


async def test_time_to_first_call_computed_from_the_oldest_real_event(harness_factory):
    h = harness_factory()
    developer = await h.developer_service.register(name="Ada", email="ada@example.com")

    first_event = developer.created_at + timedelta(minutes=5)
    second_event = developer.created_at + timedelta(minutes=20)
    h.auditability._events_by_tenant[developer.tenant_id] = [second_event, first_event]

    metrics = await h.adoption_service.time_to_first_call(developer.id)

    assert metrics.first_call_at == first_event
    assert metrics.time_to_first_call_seconds == pytest.approx(300.0, abs=1.0)


async def test_time_to_first_call_raises_not_found(harness):
    with pytest.raises(DeveloperNotFoundError):
        await harness.adoption_service.time_to_first_call("does-not-exist")


async def test_adoption_rate_with_no_developers_is_none(harness):
    report = await harness.adoption_service.adoption_rate()

    assert report.total_developers == 0
    assert report.rate is None


async def test_adoption_rate_reflects_which_developers_have_activity(harness_factory):
    h = harness_factory()
    active_dev = await h.developer_service.register(name="Ada", email="ada@example.com")
    await h.developer_service.register(name="Bea", email="bea@example.com")
    h.auditability._events_by_tenant[active_dev.tenant_id] = [datetime.now(UTC)]

    report = await h.adoption_service.adoption_rate()

    assert report.total_developers == 2
    assert report.adopted_count == 1
    assert report.rate == pytest.approx(0.5)
