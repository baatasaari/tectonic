"""Catalogue Service (LLD §2 sub-components): search listings, paginated,
`published` only by default -- the repository owns the reuse_count-first
sort order (LLD §3's own differentiator).
"""
from __future__ import annotations

from agent_marketplace.core.domain import ListingRecord, ListingStatus
from agent_marketplace.core.ports import AgentMarketplaceRepository


class CatalogueService:
    def __init__(self, repository: AgentMarketplaceRepository) -> None:
        self._repository = repository

    async def search(
        self, *, tenant_id: str | None = None, status: ListingStatus | None = ListingStatus.PUBLISHED,
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[ListingRecord], int]:
        return await self._repository.list_listings(tenant_id=tenant_id, status=status, limit=limit, offset=offset)
