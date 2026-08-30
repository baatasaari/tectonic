"""SQLAlchemy-backed implementation of LongTermMemoryRepository (LLD §3.1)."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from long_term_memory.core.domain import (
    ConsolidationRunRecord,
    DeletionRecord,
    MemoryItemRecord,
    MemoryItemStatus,
    MemoryType,
    ReflectionEntryRecord,
)
from long_term_memory.db import models


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _item_to_domain(m: models.MemoryItem) -> MemoryItemRecord:
    return MemoryItemRecord(
        id=str(m.id), tenant_id=m.tenant_id, scope=m.scope, memory_type=MemoryType(m.memory_type), content=m.content,
        visibility_policy_ref=m.visibility_policy_ref, vector_ref=m.vector_ref, graph_ref=m.graph_ref,
        status=MemoryItemStatus(m.status), relevance_score=m.relevance_score,
        created_at=_as_utc(m.created_at), last_accessed_at=_as_utc(m.last_accessed_at),
    )


def _run_to_domain(m: models.ConsolidationRun) -> ConsolidationRunRecord:
    return ConsolidationRunRecord(
        id=str(m.id), tenant_id=m.tenant_id, items_merged_count=m.items_merged_count,
        items_decayed_count=m.items_decayed_count, run_at=_as_utc(m.run_at),
    )


def _reflection_to_domain(m: models.ReflectionEntry) -> ReflectionEntryRecord:
    return ReflectionEntryRecord(
        id=str(m.id), tenant_id=m.tenant_id, agent_ref=m.agent_ref,
        triggering_interaction_ref=m.triggering_interaction_ref, reflection_content=m.reflection_content,
        applied=m.applied, created_at=_as_utc(m.created_at),
    )


def _deletion_to_domain(m: models.DeletionRecordModel) -> DeletionRecord:
    return DeletionRecord(
        id=str(m.id), tenant_id=m.tenant_id, subject_ref=m.subject_ref,
        memory_items_deleted=list(m.memory_items_deleted or []), deletion_proof_hash=m.deletion_proof_hash,
        requested_by=m.requested_by, completed_at=_as_utc(m.completed_at),
    )


class SQLAlchemyLongTermMemoryRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_item(self, record: MemoryItemRecord) -> MemoryItemRecord:
        m = models.MemoryItem(
            id=record.id, tenant_id=record.tenant_id, scope=record.scope, memory_type=record.memory_type.value,
            content=record.content, visibility_policy_ref=record.visibility_policy_ref, vector_ref=record.vector_ref,
            graph_ref=record.graph_ref, status=record.status.value, relevance_score=record.relevance_score,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _item_to_domain(m)

    async def get_item(self, tenant_id: str, item_id: str) -> MemoryItemRecord | None:
        m = await self.session.get(models.MemoryItem, item_id)
        if m is None or m.tenant_id != tenant_id:
            return None
        return _item_to_domain(m)

    async def update_item(self, record: MemoryItemRecord) -> MemoryItemRecord:
        m = await self.session.get(models.MemoryItem, record.id)
        if m is None:
            raise LookupError(record.id)
        m.vector_ref = record.vector_ref
        m.graph_ref = record.graph_ref
        m.status = record.status.value
        m.relevance_score = record.relevance_score
        m.last_accessed_at = record.last_accessed_at
        await self.session.commit()
        await self.session.refresh(m)
        return _item_to_domain(m)

    async def list_by_scope(self, tenant_id: str, scope: str) -> list[MemoryItemRecord]:
        rows = await self.session.execute(
            select(models.MemoryItem).where(models.MemoryItem.tenant_id == tenant_id, models.MemoryItem.scope == scope)
        )
        return [_item_to_domain(m) for m in rows.scalars().all()]

    async def list_active(self, tenant_id: str, memory_types: list[MemoryType] | None = None) -> list[MemoryItemRecord]:
        stmt = select(models.MemoryItem).where(
            models.MemoryItem.tenant_id == tenant_id, models.MemoryItem.status == MemoryItemStatus.ACTIVE.value,
        )
        if memory_types:
            stmt = stmt.where(models.MemoryItem.memory_type.in_([t.value for t in memory_types]))
        rows = await self.session.execute(stmt)
        return [_item_to_domain(m) for m in rows.scalars().all()]

    async def delete_items(self, tenant_id: str, item_ids: list[str]) -> None:
        for item_id in item_ids:
            m = await self.session.get(models.MemoryItem, item_id)
            if m is not None and m.tenant_id == tenant_id:
                await self.session.delete(m)
        await self.session.commit()

    async def create_consolidation_run(self, record: ConsolidationRunRecord) -> ConsolidationRunRecord:
        m = models.ConsolidationRun(
            id=record.id, tenant_id=record.tenant_id, items_merged_count=record.items_merged_count,
            items_decayed_count=record.items_decayed_count,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _run_to_domain(m)

    async def create_reflection(self, record: ReflectionEntryRecord) -> ReflectionEntryRecord:
        m = models.ReflectionEntry(
            id=record.id, tenant_id=record.tenant_id, agent_ref=record.agent_ref,
            triggering_interaction_ref=record.triggering_interaction_ref,
            reflection_content=record.reflection_content, applied=record.applied,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _reflection_to_domain(m)

    async def list_reflections(
        self, tenant_id: str, agent_ref: str, limit: int = 50, offset: int = 0
    ) -> tuple[list[ReflectionEntryRecord], int]:
        where_clause = (
            models.ReflectionEntry.tenant_id == tenant_id, models.ReflectionEntry.agent_ref == agent_ref,
        )
        total_rows = await self.session.execute(
            select(func.count(models.ReflectionEntry.id)).where(*where_clause)
        )
        total = total_rows.scalar_one()

        rows = await self.session.execute(
            select(models.ReflectionEntry)
            .where(*where_clause)
            .order_by(models.ReflectionEntry.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return [_reflection_to_domain(m) for m in rows.scalars().all()], total

    async def create_deletion_record(self, record: DeletionRecord) -> DeletionRecord:
        m = models.DeletionRecordModel(
            id=record.id, tenant_id=record.tenant_id, subject_ref=record.subject_ref,
            memory_items_deleted=record.memory_items_deleted, deletion_proof_hash=record.deletion_proof_hash,
            requested_by=record.requested_by, completed_at=record.completed_at,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _deletion_to_domain(m)

    async def get_deletion_record(self, tenant_id: str, deletion_id: str) -> DeletionRecord | None:
        m = await self.session.get(models.DeletionRecordModel, deletion_id)
        if m is None or m.tenant_id != tenant_id:
            return None
        return _deletion_to_domain(m)
