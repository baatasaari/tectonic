"""SQLAlchemy-backed implementation of ObservabilityRepository (LLD §3)."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from observability.core.domain import SpanRecord
from observability.db import models


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _span_to_domain(m: models.Span) -> SpanRecord:
    return SpanRecord(
        id=m.id, tenant_id=m.tenant_id, trace_id=m.trace_id, span_id=m.span_id, parent_span_id=m.parent_span_id,
        name=m.name, service_name=m.service_name, start_time=_as_utc(m.start_time), end_time=_as_utc(m.end_time),
        attributes=dict(m.attributes or {}), status=m.status, workflow_type=m.workflow_type,
        ingested_at=_as_utc(m.ingested_at),
    )


class SQLAlchemyObservabilityRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_span(self, record: SpanRecord) -> SpanRecord:
        m = models.Span(
            id=record.id, tenant_id=record.tenant_id, trace_id=record.trace_id, span_id=record.span_id,
            parent_span_id=record.parent_span_id, name=record.name, service_name=record.service_name,
            start_time=record.start_time, end_time=record.end_time, attributes=record.attributes,
            status=record.status, workflow_type=record.workflow_type, ingested_at=record.ingested_at,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _span_to_domain(m)

    async def list_spans_for_trace(self, tenant_id: str, trace_id: str) -> list[SpanRecord]:
        rows = await self.session.execute(
            select(models.Span).where(models.Span.tenant_id == tenant_id, models.Span.trace_id == trace_id)
        )
        return [_span_to_domain(m) for m in rows.scalars().all()]

    async def list_traces_for_tenant(
        self, tenant_id: str, *, workflow_type: str | None = None,
    ) -> list[tuple[str, str | None]]:
        stmt = select(models.Span.trace_id, models.Span.workflow_type).where(models.Span.tenant_id == tenant_id).distinct()
        if workflow_type is not None:
            stmt = stmt.where(models.Span.workflow_type == workflow_type)
        rows = await self.session.execute(stmt)
        return list(rows.all())
