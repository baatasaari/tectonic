"""Abstract ports this module depends on: persistence, and the real
Agent Cards peer client the Catalogue Sync Service reads from.
"""
from __future__ import annotations

from typing import Any, Protocol

from agent_marketplace.core.domain import ListingRecord, ListingStatus, UsageEventRecord


class AgentMarketplaceRepository(Protocol):
    async def create_listing(self, record: ListingRecord) -> ListingRecord: ...

    async def get_listing(self, listing_id: str) -> ListingRecord | None: ...

    async def update_listing(self, record: ListingRecord) -> ListingRecord: ...

    async def list_listings(
        self, *, tenant_id: str | None = None, status: ListingStatus | None = None,
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[ListingRecord], int]:
        """Sorted by reuse_count descending, ties broken by
        trust_score_snapshot descending -- LLD §2's own differentiator."""
        ...

    async def create_usage_event(self, record: UsageEventRecord) -> UsageEventRecord: ...

    async def count_usage_events(self, listing_id: str) -> tuple[int, int]:
        """Returns (total_events, distinct_consumer_tenants) for a listing."""
        ...


class AgentCardsClient(Protocol):
    async def get_card(self, card_id: str) -> dict[str, Any] | None:
        """Returns the card's `{name, description, skills, trust_score}`,
        or None if Agent Cards has no such card (a 404)."""
        ...
