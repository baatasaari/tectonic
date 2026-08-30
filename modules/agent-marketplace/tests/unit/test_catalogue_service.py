"""Tests for core/catalogue_service.py -- published-only default, reuse_count-first ranking."""
from __future__ import annotations

from agent_marketplace.core.domain import ListingStatus


async def test_search_defaults_to_published_only(harness):
    pending = await harness.governance_service.submit(tenant_id="acme", agent_card_id="card-1", submitted_by="alice")
    published = await harness.governance_service.submit(tenant_id="acme", agent_card_id="card-2", submitted_by="bob")
    await harness.governance_service.approve(published.id, reviewed_by="carol")

    listings, total = await harness.catalogue_service.search(tenant_id="acme")

    assert total == 1
    assert listings[0].id == published.id
    assert pending.id not in [listing.id for listing in listings]


async def test_search_with_an_explicit_status_returns_that_status(harness):
    pending = await harness.governance_service.submit(tenant_id="acme", agent_card_id="card-1", submitted_by="alice")

    listings, total = await harness.catalogue_service.search(tenant_id="acme", status=ListingStatus.PENDING_REVIEW)

    assert total == 1
    assert listings[0].id == pending.id


async def test_search_ranks_by_reuse_count_descending(harness):
    low = await harness.governance_service.submit(tenant_id="acme", agent_card_id="card-1", submitted_by="alice")
    high = await harness.governance_service.submit(tenant_id="acme", agent_card_id="card-2", submitted_by="bob")
    await harness.governance_service.approve(low.id, reviewed_by="carol")
    await harness.governance_service.approve(high.id, reviewed_by="carol")
    await harness.usage_tracking_service.record_usage(low.id, consumer_tenant_id="globex")
    for tenant in ("globex", "initech", "hooli"):
        await harness.usage_tracking_service.record_usage(high.id, consumer_tenant_id=tenant)

    listings, _ = await harness.catalogue_service.search(tenant_id="acme")

    assert [listing.id for listing in listings] == [high.id, low.id]
