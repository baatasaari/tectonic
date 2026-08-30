"""Catalogue Sync Service (LLD §2 sub-components): wholesale-refreshes a
listing's denormalized card snapshot (name/description/skills/trust_score)
from Agent Cards' own real card -- always a replace, never a merge, the
same convention MCP's own Capability Sync Service already established
for its own cached tool lists.
"""
from __future__ import annotations

from agent_marketplace.core.domain import (
    AgentCardNotFoundError,
    ListingNotFoundError,
    ListingRecord,
    now,
)
from agent_marketplace.core.ports import AgentCardsClient, AgentMarketplaceRepository


class CatalogueSyncService:
    def __init__(self, repository: AgentMarketplaceRepository, agent_cards: AgentCardsClient) -> None:
        self._repository = repository
        self._agent_cards = agent_cards

    async def sync(self, listing_id: str) -> ListingRecord:
        record = await self._repository.get_listing(listing_id)
        if record is None:
            raise ListingNotFoundError(listing_id)

        card = await self._agent_cards.get_card(record.agent_card_id)
        if card is None:
            raise AgentCardNotFoundError(record.agent_card_id)

        record.name = card.get("name", "")
        record.description = card.get("description", "")
        record.skills_snapshot = card.get("skills", [])
        record.trust_score_snapshot = card.get("trust_score")
        record.updated_at = now()
        return await self._repository.update_listing(record)
