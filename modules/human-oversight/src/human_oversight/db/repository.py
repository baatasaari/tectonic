"""SQLAlchemy-backed implementation of HumanOversightRepository (LLD §3)."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from human_oversight.core.domain import (
    DecisionRecord,
    DecisionType,
    NotificationLogRecord,
    OverrideRecord,
    OversightRequestRecord,
    RequestStatus,
)
from human_oversight.db import models


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _request_to_domain(m: models.OversightRequest) -> OversightRequestRecord:
    return OversightRequestRecord(
        id=str(m.id), tenant_id=m.tenant_id, requesting_module=m.requesting_module, requesting_ref=m.requesting_ref,
        context=dict(m.context or {}), priority=m.priority, status=RequestStatus(m.status), claimed_by=m.claimed_by,
        created_at=_as_utc(m.created_at), expires_at=_as_utc(m.expires_at),
    )


def _decision_to_domain(m: models.Decision) -> DecisionRecord:
    return DecisionRecord(
        id=str(m.id), request_id=str(m.request_id), decision=DecisionType(m.decision), decided_by=m.decided_by,
        decision_reason=m.decision_reason, decided_at=_as_utc(m.decided_at),
    )


def _override_to_domain(m: models.OverrideRecordModel) -> OverrideRecord:
    return OverrideRecord(
        id=str(m.id), decision_id=str(m.decision_id), original_agent_proposal=dict(m.original_agent_proposal or {}),
        human_override_action=dict(m.human_override_action or {}), override_reason=m.override_reason,
        created_at=_as_utc(m.created_at),
    )


def _notification_to_domain(m: models.NotificationLog) -> NotificationLogRecord:
    return NotificationLogRecord(
        id=str(m.id), request_id=str(m.request_id), channel=m.channel, delivered_at=_as_utc(m.delivered_at),
        delivery_status=m.delivery_status,
    )


class SQLAlchemyHumanOversightRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_request(self, record: OversightRequestRecord) -> OversightRequestRecord:
        m = models.OversightRequest(
            id=record.id, tenant_id=record.tenant_id, requesting_module=record.requesting_module,
            requesting_ref=record.requesting_ref, context=record.context, priority=record.priority,
            status=record.status.value, claimed_by=record.claimed_by, expires_at=record.expires_at,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _request_to_domain(m)

    async def get_request(self, tenant_id: str, request_id: str) -> OversightRequestRecord | None:
        m = await self.session.get(models.OversightRequest, request_id)
        if m is None or m.tenant_id != tenant_id:
            return None
        return _request_to_domain(m)

    async def update_request(self, record: OversightRequestRecord) -> OversightRequestRecord:
        m = await self.session.get(models.OversightRequest, record.id)
        if m is None:
            raise LookupError(record.id)
        m.status = record.status.value
        m.claimed_by = record.claimed_by
        await self.session.commit()
        await self.session.refresh(m)
        return _request_to_domain(m)

    async def list_requests(
        self, tenant_id: str, status: str | None = None, *, limit: int = 50, offset: int = 0,
    ) -> tuple[list[OversightRequestRecord], int]:
        stmt = select(models.OversightRequest).where(models.OversightRequest.tenant_id == tenant_id)
        count_stmt = select(func.count(models.OversightRequest.id)).where(
            models.OversightRequest.tenant_id == tenant_id
        )
        if status:
            stmt = stmt.where(models.OversightRequest.status == status)
            count_stmt = count_stmt.where(models.OversightRequest.status == status)
        stmt = stmt.order_by(models.OversightRequest.created_at.desc()).limit(limit).offset(offset)
        rows = await self.session.execute(stmt)
        total = await self.session.execute(count_stmt)
        return [_request_to_domain(m) for m in rows.scalars().all()], total.scalar_one()

    async def list_pending_expired(self, tenant_id: str, as_of: datetime) -> list[OversightRequestRecord]:
        rows = await self.session.execute(
            select(models.OversightRequest).where(
                models.OversightRequest.tenant_id == tenant_id,
                models.OversightRequest.status.in_([RequestStatus.PENDING.value, RequestStatus.CLAIMED.value]),
                models.OversightRequest.expires_at <= as_of,
            )
        )
        return [_request_to_domain(m) for m in rows.scalars().all()]

    async def create_decision(self, record: DecisionRecord) -> DecisionRecord:
        m = models.Decision(
            id=record.id, request_id=record.request_id, decision=record.decision.value,
            decided_by=record.decided_by, decision_reason=record.decision_reason,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _decision_to_domain(m)

    async def get_decision_for_request(self, request_id: str) -> DecisionRecord | None:
        rows = await self.session.execute(select(models.Decision).where(models.Decision.request_id == request_id))
        m = rows.scalars().first()
        return _decision_to_domain(m) if m else None

    async def create_override_record(self, record: OverrideRecord) -> OverrideRecord:
        m = models.OverrideRecordModel(
            id=record.id, decision_id=record.decision_id, original_agent_proposal=record.original_agent_proposal,
            human_override_action=record.human_override_action, override_reason=record.override_reason,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _override_to_domain(m)

    async def get_override_for_decision(self, decision_id: str) -> OverrideRecord | None:
        rows = await self.session.execute(
            select(models.OverrideRecordModel).where(models.OverrideRecordModel.decision_id == decision_id)
        )
        m = rows.scalars().first()
        return _override_to_domain(m) if m else None

    async def create_notification_log(self, record: NotificationLogRecord) -> NotificationLogRecord:
        m = models.NotificationLog(
            id=record.id, request_id=record.request_id, channel=record.channel,
            delivered_at=record.delivered_at, delivery_status=record.delivery_status,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _notification_to_domain(m)
