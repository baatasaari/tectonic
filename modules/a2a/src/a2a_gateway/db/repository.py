"""SQLAlchemy-backed implementation of A2AGatewayRepository (LLD §3)."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from a2a_gateway.core.domain import (
    A2AAccessPolicyRecord,
    A2ATaskRecord,
    AgentCardCacheEntry,
    TaskDirection,
    TaskStatus,
)
from a2a_gateway.db import models


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _task_to_domain(m: models.A2ATask) -> A2ATaskRecord:
    return A2ATaskRecord(
        id=str(m.id), tenant_id=m.tenant_id, direction=TaskDirection(m.direction), peer_agent_url=m.peer_agent_url,
        skill_id=m.skill_id, status=TaskStatus(m.status), input_message=dict(m.input_message or {}),
        output_artifacts=list(m.output_artifacts or []), error=m.error,
        created_at=_as_utc(m.created_at), updated_at=_as_utc(m.updated_at),
    )


def _policy_to_domain(m: models.A2AAccessPolicy) -> A2AAccessPolicyRecord:
    return A2AAccessPolicyRecord(
        id=str(m.id), caller_agent_id=m.caller_agent_id, tenant_id=m.tenant_id,
        allowed_skills=list(m.allowed_skills) if m.allowed_skills is not None else None,
    )


def _card_to_domain(m: models.AgentCardCache) -> AgentCardCacheEntry:
    return AgentCardCacheEntry(
        id=str(m.id), agent_url=m.agent_url, card=dict(m.card or {}),
        fetched_at=_as_utc(m.fetched_at), expires_at=_as_utc(m.expires_at),
    )


class SQLAlchemyA2AGatewayRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_task(self, record: A2ATaskRecord) -> A2ATaskRecord:
        m = models.A2ATask(
            id=record.id, tenant_id=record.tenant_id, direction=record.direction.value,
            peer_agent_url=record.peer_agent_url, skill_id=record.skill_id, status=record.status.value,
            input_message=record.input_message, output_artifacts=record.output_artifacts,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _task_to_domain(m)

    async def get_task(self, task_id: str) -> A2ATaskRecord | None:
        m = await self.session.get(models.A2ATask, task_id)
        return _task_to_domain(m) if m else None

    async def update_task_status(
        self, task_id: str, *, status: TaskStatus, output_artifacts: list[dict[str, Any]] | None = None,
        error: str | None = None,
    ) -> A2ATaskRecord:
        m = await self.session.get(models.A2ATask, task_id)
        m.status = TaskStatus(status).value
        if output_artifacts is not None:
            m.output_artifacts = output_artifacts
        if error is not None:
            m.error = error
        await self.session.commit()
        await self.session.refresh(m)
        return _task_to_domain(m)

    async def list_tasks(
        self, *, tenant_id: str | None = None, direction: TaskDirection | None = None,
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[A2ATaskRecord], int]:
        filters = []
        if tenant_id is not None:
            filters.append(models.A2ATask.tenant_id == tenant_id)
        if direction is not None:
            filters.append(models.A2ATask.direction == direction.value)

        count_stmt = select(func.count(models.A2ATask.id)).where(*filters)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            select(models.A2ATask).where(*filters).order_by(models.A2ATask.created_at.desc())
            .limit(limit).offset(offset)
        )
        rows = await self.session.execute(stmt)
        return [_task_to_domain(m) for m in rows.scalars().all()], total

    async def upsert_access_policy(self, record: A2AAccessPolicyRecord) -> A2AAccessPolicyRecord:
        rows = await self.session.execute(
            select(models.A2AAccessPolicy).where(
                models.A2AAccessPolicy.caller_agent_id == record.caller_agent_id,
                models.A2AAccessPolicy.tenant_id == record.tenant_id,
            )
        )
        existing = rows.scalars().first()
        if existing is not None:
            existing.allowed_skills = record.allowed_skills
            await self.session.commit()
            await self.session.refresh(existing)
            return _policy_to_domain(existing)

        m = models.A2AAccessPolicy(
            id=record.id, caller_agent_id=record.caller_agent_id, tenant_id=record.tenant_id,
            allowed_skills=record.allowed_skills,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _policy_to_domain(m)

    async def get_access_policy(self, caller_agent_id: str, tenant_id: str) -> A2AAccessPolicyRecord | None:
        rows = await self.session.execute(
            select(models.A2AAccessPolicy).where(
                models.A2AAccessPolicy.caller_agent_id == caller_agent_id,
                models.A2AAccessPolicy.tenant_id == tenant_id,
            )
        )
        m = rows.scalars().first()
        return _policy_to_domain(m) if m else None

    async def get_cached_card(self, agent_url: str) -> AgentCardCacheEntry | None:
        rows = await self.session.execute(
            select(models.AgentCardCache).where(models.AgentCardCache.agent_url == agent_url)
        )
        m = rows.scalars().first()
        return _card_to_domain(m) if m else None

    async def upsert_cached_card(self, entry: AgentCardCacheEntry) -> AgentCardCacheEntry:
        rows = await self.session.execute(
            select(models.AgentCardCache).where(models.AgentCardCache.agent_url == entry.agent_url)
        )
        existing = rows.scalars().first()
        if existing is not None:
            existing.card = entry.card
            existing.fetched_at = entry.fetched_at
            existing.expires_at = entry.expires_at
            await self.session.commit()
            await self.session.refresh(existing)
            return _card_to_domain(existing)

        m = models.AgentCardCache(
            id=entry.id, agent_url=entry.agent_url, card=entry.card,
            fetched_at=entry.fetched_at, expires_at=entry.expires_at,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _card_to_domain(m)
