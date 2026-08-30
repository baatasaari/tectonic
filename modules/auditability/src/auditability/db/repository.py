"""SQLAlchemy-backed implementation of AuditabilityRepository (LLD §3)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from auditability.core.domain import (
    AuditEventFilter,
    AuditEventRecord,
    AuditPackRecord,
    AuditPackStatus,
    now,
)
from auditability.core.hash_chain import compute_entry_hash
from auditability.db import models


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _event_to_domain(m: models.AuditEvent) -> AuditEventRecord:
    return AuditEventRecord(
        id=str(m.id), tenant_id=m.tenant_id, source_module=m.source_module, event_type=m.event_type,
        payload=dict(m.payload or {}), sequence_number=m.sequence_number, entry_hash=m.entry_hash,
        prev_hash=m.prev_hash, occurred_at=_as_utc(m.occurred_at),
    )


def _pack_to_domain(m: models.AuditPack) -> AuditPackRecord:
    return AuditPackRecord(
        id=str(m.id), tenant_id=m.tenant_id, status=AuditPackStatus(m.status),
        filter_event_type=m.filter_event_type, filter_source_module=m.filter_source_module,
        filter_control_name=m.filter_control_name, filter_occurred_after=_as_utc(m.filter_occurred_after),
        filter_occurred_before=_as_utc(m.filter_occurred_before), event_count=m.event_count,
        chain_valid=m.chain_valid, generated_at=_as_utc(m.generated_at), document_ref=m.document_ref,
        document_format=m.document_format, document_bytes_b64=m.document_bytes_b64,
        created_at=_as_utc(m.created_at), worker_id=m.worker_id, lease_expires_at=_as_utc(m.lease_expires_at),
        attempts=m.attempts, last_error=m.last_error,
    )


class SQLAlchemyAuditabilityRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def append_event(
        self, *, tenant_id: str, source_module: str, event_type: str, payload: dict[str, Any],
    ) -> AuditEventRecord:
        # A Postgres transaction-scoped advisory lock keyed on tenant_id, taken BEFORE
        # the read -- this is what actually serializes concurrent writers for the same
        # tenant. `SELECT ... FOR UPDATE` on the tenant's last row alone is not enough:
        # Postgres row locks only apply to rows that already exist, so a brand-new
        # tenant's very first event has no row to lock at all, and concurrent first
        # writers would all read "no prior row" and race to insert sequence_number=1
        # (caught for real by tests/integration/test_concurrency_postgres.py, not by
        # reasoning about the SQL in the abstract). The advisory lock closes that gap
        # regardless of whether any row exists yet; released automatically at commit.
        # Deliberately not SKIP LOCKED: correctness here requires every write for a
        # tenant to see the immediately preceding one, never to skip past a concurrent
        # writer the way the audit-pack queue's claim does. Different tenants never
        # contend with each other since the lock key is scoped per tenant_id.
        await self.session.execute(select(func.pg_advisory_xact_lock(func.hashtext(tenant_id))))

        stmt = (
            select(models.AuditEvent)
            .where(models.AuditEvent.tenant_id == tenant_id)
            .order_by(models.AuditEvent.sequence_number.desc())
            .limit(1)
            .with_for_update()
        )
        rows = await self.session.execute(stmt)
        prior = rows.scalars().first()
        sequence_number = (prior.sequence_number + 1) if prior else 1
        prev_hash = prior.entry_hash if prior else None
        occurred_at = now()
        entry_hash = compute_entry_hash(
            sequence_number=sequence_number, tenant_id=tenant_id, source_module=source_module,
            event_type=event_type, occurred_at=occurred_at, payload=payload, prev_hash=prev_hash,
        )
        m = models.AuditEvent(
            tenant_id=tenant_id, source_module=source_module, event_type=event_type, payload=payload,
            sequence_number=sequence_number, prev_hash=prev_hash, entry_hash=entry_hash, occurred_at=occurred_at,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _event_to_domain(m)

    async def list_events(self, event_filter: AuditEventFilter) -> tuple[list[AuditEventRecord], int]:
        filters = [models.AuditEvent.tenant_id == event_filter.tenant_id]
        if event_filter.event_type is not None:
            filters.append(models.AuditEvent.event_type == event_filter.event_type)
        if event_filter.source_module is not None:
            filters.append(models.AuditEvent.source_module == event_filter.source_module)
        if event_filter.control_name is not None:
            filters.append(models.AuditEvent.payload["control_name"].as_string() == event_filter.control_name)
        if event_filter.occurred_after is not None:
            filters.append(models.AuditEvent.occurred_at >= event_filter.occurred_after)
        if event_filter.occurred_before is not None:
            filters.append(models.AuditEvent.occurred_at <= event_filter.occurred_before)

        count_stmt = select(func.count(models.AuditEvent.id)).where(*filters)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            select(models.AuditEvent)
            .where(*filters)
            .order_by(models.AuditEvent.sequence_number.desc())
            .limit(event_filter.limit)
            .offset(event_filter.offset)
        )
        rows = await self.session.execute(stmt)
        return [_event_to_domain(m) for m in rows.scalars().all()], total

    async def list_events_for_chain(self, tenant_id: str) -> list[AuditEventRecord]:
        rows = await self.session.execute(
            select(models.AuditEvent)
            .where(models.AuditEvent.tenant_id == tenant_id)
            .order_by(models.AuditEvent.sequence_number.asc())
        )
        return [_event_to_domain(m) for m in rows.scalars().all()]

    async def create_audit_pack(self, record: AuditPackRecord) -> AuditPackRecord:
        m = models.AuditPack(
            id=record.id, tenant_id=record.tenant_id, status=record.status.value,
            filter_event_type=record.filter_event_type, filter_source_module=record.filter_source_module,
            filter_control_name=record.filter_control_name, filter_occurred_after=record.filter_occurred_after,
            filter_occurred_before=record.filter_occurred_before, document_format=record.document_format,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _pack_to_domain(m)

    async def update_audit_pack(self, record: AuditPackRecord) -> AuditPackRecord:
        m = await self.session.get(models.AuditPack, record.id)
        if m is None:
            raise ValueError(f"audit pack not found: {record.id}")
        m.status = record.status.value
        m.event_count = record.event_count
        m.chain_valid = record.chain_valid
        m.generated_at = record.generated_at
        m.document_ref = record.document_ref
        m.document_format = record.document_format
        m.document_bytes_b64 = record.document_bytes_b64
        m.last_error = record.last_error
        await self.session.commit()
        await self.session.refresh(m)
        return _pack_to_domain(m)

    async def get_audit_pack(self, tenant_id: str, pack_id: str) -> AuditPackRecord | None:
        m = await self.session.get(models.AuditPack, pack_id)
        if m is None or m.tenant_id != tenant_id:
            return None
        return _pack_to_domain(m)

    async def claim_next_audit_pack(self, worker_id: str, lease_seconds: int) -> AuditPackRecord | None:
        """`SELECT ... FOR UPDATE SKIP LOCKED`: the row-level lock this takes is what
        lets multiple worker processes/pods poll concurrently without two of them ever
        claiming the same pending pack — a competing claimant simply skips a row another
        transaction already has locked, rather than blocking on it or double-claiming it."""
        moment = now()
        stmt = (
            select(models.AuditPack)
            .where(
                models.AuditPack.status == AuditPackStatus.GENERATING.value,
                (models.AuditPack.lease_expires_at.is_(None)) | (models.AuditPack.lease_expires_at < moment),
            )
            .order_by(models.AuditPack.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        rows = await self.session.execute(stmt)
        m = rows.scalars().first()
        if m is None:
            return None
        m.worker_id = worker_id
        m.attempts += 1
        m.lease_expires_at = moment + timedelta(seconds=lease_seconds)
        await self.session.commit()
        await self.session.refresh(m)
        return _pack_to_domain(m)

    async def requeue_audit_pack_for_retry(self, pack_id: str) -> None:
        m = await self.session.get(models.AuditPack, pack_id)
        if m is None:
            return
        m.status = AuditPackStatus.GENERATING.value
        m.lease_expires_at = None
        await self.session.commit()

    async def fail_exhausted_audit_packs(self, max_attempts: int) -> int:
        result = await self.session.execute(
            update(models.AuditPack)
            .where(
                models.AuditPack.status == AuditPackStatus.GENERATING.value,
                models.AuditPack.attempts >= max_attempts,
            )
            .values(status=AuditPackStatus.FAILED.value, last_error=f"exceeded max attempts ({max_attempts})")
        )
        await self.session.commit()
        return result.rowcount or 0

    async def force_expire_stale_leases(self) -> int:
        moment = now()
        result = await self.session.execute(
            update(models.AuditPack)
            .where(
                models.AuditPack.status == AuditPackStatus.GENERATING.value,
                models.AuditPack.lease_expires_at.is_not(None),
                models.AuditPack.lease_expires_at > moment,
            )
            .values(lease_expires_at=moment)
        )
        await self.session.commit()
        return result.rowcount or 0
