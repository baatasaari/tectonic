"""Governance Service (LLD §2 sub-components, §Level 3 "The governance
state machine"): submit / approve / reject / deprecate. Rejects any
transition not explicitly legal (`domain.is_legal_transition`) rather
than silently allowing an out-of-order state change.
"""
from __future__ import annotations

from agent_marketplace.core.domain import (
    AgentCardNotFoundError,
    InvalidTransitionError,
    ListingNotFoundError,
    ListingRecord,
    ListingStatus,
    is_legal_transition,
    new_id,
    now,
)
from agent_marketplace.core.ports import AgentCardsClient, AgentMarketplaceRepository


class GovernanceService:
    def __init__(self, repository: AgentMarketplaceRepository, agent_cards: AgentCardsClient) -> None:
        self._repository = repository
        self._agent_cards = agent_cards

    async def submit(
        self, *, tenant_id: str, agent_card_id: str, submitted_by: str, external_listing_enabled: bool = False,
    ) -> ListingRecord:
        card = await self._agent_cards.get_card(agent_card_id)
        if card is None:
            raise AgentCardNotFoundError(agent_card_id)

        record = ListingRecord(
            id=new_id(), tenant_id=tenant_id, agent_card_id=agent_card_id, name=card.get("name", ""),
            description=card.get("description", ""), skills_snapshot=card.get("skills", []),
            trust_score_snapshot=card.get("trust_score"), submitted_by=submitted_by,
            external_listing_enabled=external_listing_enabled,
        )
        return await self._repository.create_listing(record)

    async def _get(self, listing_id: str) -> ListingRecord:
        record = await self._repository.get_listing(listing_id)
        if record is None:
            raise ListingNotFoundError(listing_id)
        return record

    async def _transition(self, listing_id: str, to_status: ListingStatus, **fields) -> ListingRecord:
        record = await self._get(listing_id)
        if not is_legal_transition(record.status, to_status):
            raise InvalidTransitionError(record.status, to_status)

        record.status = to_status
        for key, value in fields.items():
            setattr(record, key, value)
        record.updated_at = now()
        return await self._repository.update_listing(record)

    async def approve(self, listing_id: str, *, reviewed_by: str) -> ListingRecord:
        return await self._transition(
            listing_id, ListingStatus.PUBLISHED, reviewed_by=reviewed_by, reviewed_at=now(),
        )

    async def reject(self, listing_id: str, *, reviewed_by: str, reason: str) -> ListingRecord:
        return await self._transition(
            listing_id, ListingStatus.REJECTED, reviewed_by=reviewed_by, reviewed_at=now(), rejection_reason=reason,
        )

    async def deprecate(self, listing_id: str) -> ListingRecord:
        return await self._transition(listing_id, ListingStatus.DEPRECATED)
