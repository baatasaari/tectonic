"""SQLAlchemy-backed implementation of LongTermMemoryRepository (LLD §3.1)."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from long_term_memory.core.domain import (
    ConsentBasis,
    ConsentRecord,
    ConsolidationRunRecord,
    DeletionRecord,
    LegalHoldRecord,
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


def _is_valid_uuid(value: str) -> bool:
    """`id` columns are Postgres `UUID`; a caller-supplied `str` that
    isn't a syntactically valid UUID by definition names no row, but
    handing it to `asyncpg` regardless raises an unhandled
    `ValueError`/`DataError` deep in the driver instead of a clean
    `None`/404 (the same fix Multi-tenancy's, Billing and Metering's,
    and Identity and Access's own `db/repository.py` already
    established -- applied here proactively for these two new
    lookup-by-externally-supplied-id methods, not found by a contract
    tier this module doesn't have yet)."""
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False


def _item_to_domain(m: models.MemoryItem) -> MemoryItemRecord:
    return MemoryItemRecord(
        id=str(m.id), tenant_id=m.tenant_id, scope=m.scope, memory_type=MemoryType(m.memory_type), content=m.content,
        visibility_policy_ref=m.visibility_policy_ref, purpose=m.purpose, vector_ref=m.vector_ref,
        graph_ref=m.graph_ref, status=MemoryItemStatus(m.status), relevance_score=m.relevance_score,
        created_at=_as_utc(m.created_at), last_accessed_at=_as_utc(m.last_accessed_at),
    )


def _consent_to_domain(m: models.ConsentRecordModel) -> ConsentRecord:
    return ConsentRecord(
        id=str(m.id), tenant_id=m.tenant_id, scope=m.scope, purpose=m.purpose, basis=ConsentBasis(m.basis),
        granted_by=m.granted_by, granted_at=_as_utc(m.granted_at), revoked_at=_as_utc(m.revoked_at),
    )


def _legal_hold_to_domain(m: models.LegalHoldModel) -> LegalHoldRecord:
    return LegalHoldRecord(
        id=str(m.id), tenant_id=m.tenant_id, scope=m.scope, reason=m.reason, placed_by=m.placed_by,
        placed_at=_as_utc(m.placed_at), released_at=_as_utc(m.released_at),
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
            content=record.content, visibility_policy_ref=record.visibility_policy_ref, purpose=record.purpose,
            vector_ref=record.vector_ref, graph_ref=record.graph_ref, status=record.status.value,
            relevance_score=record.relevance_score,
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

    async def create_consent_record(self, record: ConsentRecord) -> ConsentRecord:
        m = models.ConsentRecordModel(
            id=record.id, tenant_id=record.tenant_id, scope=record.scope, purpose=record.purpose,
            basis=record.basis.value, granted_by=record.granted_by,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _consent_to_domain(m)

    async def get_active_consent(self, tenant_id: str, scope: str, purpose: str) -> ConsentRecord | None:
        stmt = (
            select(models.ConsentRecordModel)
            .where(
                models.ConsentRecordModel.tenant_id == tenant_id,
                models.ConsentRecordModel.scope == scope,
                models.ConsentRecordModel.purpose == purpose,
                models.ConsentRecordModel.revoked_at.is_(None),
            )
            .order_by(models.ConsentRecordModel.granted_at.desc())
        )
        m = (await self.session.execute(stmt)).scalars().first()
        return _consent_to_domain(m) if m else None

    async def revoke_consent(self, tenant_id: str, consent_id: str) -> ConsentRecord | None:
        if not _is_valid_uuid(consent_id):
            return None
        m = await self.session.get(models.ConsentRecordModel, consent_id)
        if m is None or m.tenant_id != tenant_id:
            return None
        m.revoked_at = datetime.now(UTC)
        await self.session.commit()
        await self.session.refresh(m)
        return _consent_to_domain(m)

    async def list_consents(self, tenant_id: str, scope: str) -> list[ConsentRecord]:
        rows = await self.session.execute(
            select(models.ConsentRecordModel)
            .where(models.ConsentRecordModel.tenant_id == tenant_id, models.ConsentRecordModel.scope == scope)
            .order_by(models.ConsentRecordModel.granted_at.desc())
        )
        return [_consent_to_domain(m) for m in rows.scalars().all()]

    async def create_legal_hold(self, record: LegalHoldRecord) -> LegalHoldRecord:
        m = models.LegalHoldModel(
            id=record.id, tenant_id=record.tenant_id, scope=record.scope, reason=record.reason,
            placed_by=record.placed_by,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _legal_hold_to_domain(m)

    async def get_active_legal_hold(self, tenant_id: str, scope: str) -> LegalHoldRecord | None:
        stmt = (
            select(models.LegalHoldModel)
            .where(
                models.LegalHoldModel.tenant_id == tenant_id,
                models.LegalHoldModel.scope == scope,
                models.LegalHoldModel.released_at.is_(None),
            )
            .order_by(models.LegalHoldModel.placed_at.desc())
        )
        m = (await self.session.execute(stmt)).scalars().first()
        return _legal_hold_to_domain(m) if m else None

    async def release_legal_hold(self, tenant_id: str, hold_id: str) -> LegalHoldRecord | None:
        if not _is_valid_uuid(hold_id):
            return None
        m = await self.session.get(models.LegalHoldModel, hold_id)
        if m is None or m.tenant_id != tenant_id:
            return None
        m.released_at = datetime.now(UTC)
        await self.session.commit()
        await self.session.refresh(m)
        return _legal_hold_to_domain(m)

    async def list_legal_holds(self, tenant_id: str, scope: str) -> list[LegalHoldRecord]:
        rows = await self.session.execute(
            select(models.LegalHoldModel)
            .where(models.LegalHoldModel.tenant_id == tenant_id, models.LegalHoldModel.scope == scope)
            .order_by(models.LegalHoldModel.placed_at.desc())
        )
        return [_legal_hold_to_domain(m) for m in rows.scalars().all()]
