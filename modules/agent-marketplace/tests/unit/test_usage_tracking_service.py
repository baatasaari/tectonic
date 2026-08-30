"""Tests for core/usage_tracking_service.py -- reuse_count is recomputed
from the real event log, never just incremented."""
from __future__ import annotations

import pytest

from agent_marketplace.core.domain import ListingNotFoundError


async def test_record_usage_raises_for_an_unknown_listing(harness):
    with pytest.raises(ListingNotFoundError):
        await harness.usage_tracking_service.record_usage("does-not-exist", consumer_tenant_id="globex")


async def test_record_usage_increments_reuse_count_and_persists_it_on_the_listing(harness):
    listing = await harness.governance_service.submit(tenant_id="acme", agent_card_id="card-1", submitted_by="alice")

    metrics = await harness.usage_tracking_service.record_usage(listing.id, consumer_tenant_id="globex")

    assert metrics.reuse_count == 1
    persisted = await harness.repository.get_listing(listing.id)
    assert persisted.reuse_count == 1


async def test_reuse_metrics_counts_distinct_consumer_tenants_separately_from_total_events(harness):
    listing = await harness.governance_service.submit(tenant_id="acme", agent_card_id="card-1", submitted_by="alice")
    await harness.usage_tracking_service.record_usage(listing.id, consumer_tenant_id="globex")
    await harness.usage_tracking_service.record_usage(listing.id, consumer_tenant_id="globex")
    await harness.usage_tracking_service.record_usage(listing.id, consumer_tenant_id="initech")

    metrics = await harness.usage_tracking_service.reuse_metrics(listing.id)

    assert metrics.reuse_count == 3
    assert metrics.distinct_consumer_tenants == 2


async def test_reuse_metrics_raises_for_an_unknown_listing(harness):
    with pytest.raises(ListingNotFoundError):
        await harness.usage_tracking_service.reuse_metrics("does-not-exist")
