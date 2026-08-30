"""Usage Tracking Service (LLD §2 sub-components): records a genuine
reuse event and keeps the listing's denormalized `reuse_count` in sync
with the real event log -- recomputed from `count_usage_events` on every
record, not just incremented, so the two can never drift apart.
"""
from __future__ import annotations

from agent_marketplace.core.domain import (
    ListingNotFoundError,
    ReuseMetrics,
    UsageEventRecord,
    new_id,
    now,
)
from agent_marketplace.core.ports import AgentMarketplaceRepository


class UsageTrackingService:
    def __init__(self, repository: AgentMarketplaceRepository) -> None:
        self._repository = repository

    async def record_usage(self, listing_id: str, *, consumer_tenant_id: str) -> ReuseMetrics:
        listing = await self._repository.get_listing(listing_id)
        if listing is None:
            raise ListingNotFoundError(listing_id)

        await self._repository.create_usage_event(
            UsageEventRecord(id=new_id(), listing_id=listing_id, consumer_tenant_id=consumer_tenant_id)
        )

        total, distinct = await self._repository.count_usage_events(listing_id)
        listing.reuse_count = total
        listing.updated_at = now()
        await self._repository.update_listing(listing)

        return ReuseMetrics(reuse_count=total, distinct_consumer_tenants=distinct)

    async def reuse_metrics(self, listing_id: str) -> ReuseMetrics:
        listing = await self._repository.get_listing(listing_id)
        if listing is None:
            raise ListingNotFoundError(listing_id)

        total, distinct = await self._repository.count_usage_events(listing_id)
        return ReuseMetrics(reuse_count=total, distinct_consumer_tenants=distinct)
