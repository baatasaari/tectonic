"""SQLAlchemy-backed implementation of AgentCardsRepository (LLD §3)."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_cards.core.domain import AgentCardRecord, skills_from_dicts, skills_to_dicts
from agent_cards.db import models


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _to_domain(m: models.AgentCard) -> AgentCardRecord:
    return AgentCardRecord(
        id=str(m.id), tenant_id=m.tenant_id, agent_ref=m.agent_ref, name=m.name, description=m.description,
        url=m.url, skills=skills_from_dicts(m.skills or []), trust_score=m.trust_score,
        trust_score_computed_at=_as_utc(m.trust_score_computed_at), last_verified_at=_as_utc(m.last_verified_at),
        created_at=_as_utc(m.created_at), updated_at=_as_utc(m.updated_at),
    )


class SQLAlchemyAgentCardsRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_card(self, record: AgentCardRecord) -> AgentCardRecord:
        m = models.AgentCard(
            id=record.id, tenant_id=record.tenant_id, agent_ref=record.agent_ref, name=record.name,
            description=record.description, url=record.url, skills=skills_to_dicts(record.skills),
            trust_score=record.trust_score, trust_score_computed_at=record.trust_score_computed_at,
            last_verified_at=record.last_verified_at,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _to_domain(m)

    async def get_card(self, card_id: str) -> AgentCardRecord | None:
        m = await self.session.get(models.AgentCard, card_id)
        return _to_domain(m) if m else None

    async def update_card(self, record: AgentCardRecord) -> AgentCardRecord:
        m = await self.session.get(models.AgentCard, record.id)
        m.name = record.name
        m.description = record.description
        m.url = record.url
        m.skills = skills_to_dicts(record.skills)
        m.trust_score = record.trust_score
        m.trust_score_computed_at = record.trust_score_computed_at
        m.last_verified_at = record.last_verified_at
        await self.session.commit()
        await self.session.refresh(m)
        return _to_domain(m)

    async def list_cards(
        self, *, tenant_id: str | None = None, skill_id: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[AgentCardRecord], int]:
        filters = []
        if tenant_id is not None:
            filters.append(models.AgentCard.tenant_id == tenant_id)
        if skill_id is not None:
            # JSONB containment (@>): true when some element of `skills` has at least the
            # given key/value -- exactly "this card advertises a skill with this id",
            # without requiring an exact full-object match. Postgres-only; the skill_id
            # filter path is exercised for real in the integration tier, not the SQLite
            # unit tier (see InMemoryAgentCardsRepository's own, portable equivalent).
            filters.append(models.AgentCard.skills.contains([{"id": skill_id}]))

        count_stmt = select(func.count(models.AgentCard.id)).where(*filters)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            select(models.AgentCard)
            .where(*filters)
            .order_by(models.AgentCard.trust_score.desc().nulls_last(), models.AgentCard.created_at)
            .limit(limit)
            .offset(offset)
        )
        rows = await self.session.execute(stmt)
        return [_to_domain(m) for m in rows.scalars().all()], total
