"""In-memory fakes for unit tests (LLD "Deployability and testability
contract")."""
from __future__ import annotations

from typing import Any

from agent_marketplace.core.domain import ListingRecord, ListingStatus, UsageEventRecord


class InMemoryAgentMarketplaceRepository:
    def __init__(self) -> None:
        self.listings: dict[str, ListingRecord] = {}
        self.usage_events: list[UsageEventRecord] = []

    async def create_listing(self, record: ListingRecord) -> ListingRecord:
        self.listings[record.id] = record
        return record

    async def get_listing(self, listing_id: str) -> ListingRecord | None:
        return self.listings.get(listing_id)

    async def update_listing(self, record: ListingRecord) -> ListingRecord:
        self.listings[record.id] = record
        return record

    async def list_listings(
        self, *, tenant_id: str | None = None, status: ListingStatus | None = None,
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[ListingRecord], int]:
        results = list(self.listings.values())
        if tenant_id is not None:
            results = [listing for listing in results if listing.tenant_id == tenant_id]
        if status is not None:
            results = [listing for listing in results if listing.status == status]
        results = sorted(
            results, key=lambda listing: (-listing.reuse_count, -(listing.trust_score_snapshot or 0.0), listing.created_at),
        )
        return results[offset:offset + limit], len(results)

    async def create_usage_event(self, record: UsageEventRecord) -> UsageEventRecord:
        self.usage_events.append(record)
        return record

    async def count_usage_events(self, listing_id: str) -> tuple[int, int]:
        events = [e for e in self.usage_events if e.listing_id == listing_id]
        return len(events), len({e.consumer_tenant_id for e in events})


_DEFAULT_CARD: dict[str, Any] = {
    "name": "Search Agent", "description": "Finds things", "skills": [{"id": "search", "name": "Search"}],
    "trust_score": 0.8,
}
_UNSET = object()  # distinguishes "card not passed" (use the default) from "card=None" (no such card)


class StubAgentCardsClient:
    def __init__(self, *, card: dict[str, Any] | None | object = _UNSET) -> None:
        self.calls: list[dict] = []
        self._card = _DEFAULT_CARD if card is _UNSET else card

    async def get_card(self, card_id: str) -> dict[str, Any] | None:
        self.calls.append({"card_id": card_id})
        return self._card


__all__ = ["InMemoryAgentMarketplaceRepository", "StubAgentCardsClient"]
