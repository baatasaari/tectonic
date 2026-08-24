"""Registry Service (LLD §2 sub-components): CRUD for Agent Cards --
register, fetch, update, bump `last_verified_at`.
"""
from __future__ import annotations

from typing import Any

from agent_cards.core.domain import AgentCardNotFoundError, AgentCardRecord, AgentSkill, new_id, now
from agent_cards.core.ports import AgentCardsRepository


class RegistryService:
    def __init__(self, repository: AgentCardsRepository) -> None:
        self._repository = repository

    async def register(
        self, *, tenant_id: str, agent_ref: str, name: str, description: str, url: str, skills: list[AgentSkill],
    ) -> AgentCardRecord:
        record = AgentCardRecord(
            id=new_id(), tenant_id=tenant_id, agent_ref=agent_ref, name=name, description=description, url=url,
            skills=skills,
        )
        return await self._repository.create_card(record)

    async def get(self, card_id: str) -> AgentCardRecord:
        record = await self._repository.get_card(card_id)
        if record is None:
            raise AgentCardNotFoundError(card_id)
        return record

    async def update(self, card_id: str, **fields: Any) -> AgentCardRecord:
        record = await self.get(card_id)
        for key, value in fields.items():
            if value is not None:
                setattr(record, key, value)
        record.last_verified_at = now()
        record.updated_at = now()
        return await self._repository.update_card(record)

    async def list(
        self, *, tenant_id: str | None = None, skill_id: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[AgentCardRecord], int]:
        return await self._repository.list_cards(tenant_id=tenant_id, skill_id=skill_id, limit=limit, offset=offset)
