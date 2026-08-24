"""Discovery Service (LLD §2 sub-components): search cards by
tenant/skill, paginated, sorted by trust_score descending -- the
repository owns the sort order (LLD §3's "ranks by trust score, not
registration order"); this service's own job is pairing each result
with its computed `is_stale` flag.
"""
from __future__ import annotations

from agent_cards.core.domain import AgentCardRecord
from agent_cards.core.ports import AgentCardsRepository


class DiscoveryService:
    def __init__(self, repository: AgentCardsRepository, *, staleness_ttl_seconds: int = 86400) -> None:
        self._repository = repository
        self._staleness_ttl_seconds = staleness_ttl_seconds

    async def search(
        self, *, tenant_id: str | None = None, skill_id: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[tuple[AgentCardRecord, bool]], int]:
        """Returns `[(card, is_stale), ...]` alongside the total count."""
        cards, total = await self._repository.list_cards(tenant_id=tenant_id, skill_id=skill_id, limit=limit, offset=offset)
        results = [(card, card.is_stale(ttl_seconds=self._staleness_ttl_seconds)) for card in cards]
        return results, total
