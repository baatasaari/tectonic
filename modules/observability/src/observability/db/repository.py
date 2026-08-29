"""SQLAlchemy-backed implementation of ObservabilityRepository (LLD §3)."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from observability.core.domain import (
    AlertComparison,
    AlertEvent,
    AlertRule,
    AlertStatus,
    SLODefinition,
    SLOMetric,
    SpanRecord,
    TraceSummary,
)
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


def _slo_to_domain(m: models.SLO) -> SLODefinition:
    return SLODefinition(
        id=str(m.id), tenant_id=m.tenant_id, name=m.name, metric=SLOMetric(m.metric), target=m.target,
        window_hours=m.window_hours, service_name=m.service_name, created_at=_as_utc(m.created_at),
    )


def _alert_rule_to_domain(m: models.AlertRule) -> AlertRule:
    return AlertRule(
        id=str(m.id), tenant_id=m.tenant_id, name=m.name, metric=SLOMetric(m.metric),
        comparison=AlertComparison(m.comparison), threshold=m.threshold, window_hours=m.window_hours,
        service_name=m.service_name, enabled=m.enabled, created_at=_as_utc(m.created_at),
    )


def _alert_event_to_domain(m: models.AlertEvent) -> AlertEvent:
    return AlertEvent(
        id=str(m.id), rule_id=m.rule_id, tenant_id=m.tenant_id, status=AlertStatus(m.status), value=m.value,
        threshold=m.threshold, triggered_at=_as_utc(m.triggered_at), resolved_at=_as_utc(m.resolved_at),
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

    async def list_trace_summaries(
        self, tenant_id: str, *, workflow_type: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[TraceSummary], int]:
        # A real aggregate query -- span count, time range, and whether any span in
        # the trace errored -- computed by Postgres, never by pulling every span for
        # every trace client-side just to summarize it.
        filters = [models.Span.tenant_id == tenant_id]
        if workflow_type is not None:
            filters.append(models.Span.workflow_type == workflow_type)

        count_stmt = select(func.count(func.distinct(models.Span.trace_id))).where(*filters)
        total = (await self.session.execute(count_stmt)).scalar_one()

        agg_stmt = (
            select(
                models.Span.trace_id, models.Span.workflow_type, func.count(models.Span.id).label("span_count"),
                func.min(models.Span.start_time).label("start_time"), func.max(models.Span.end_time).label("end_time"),
                func.bool_or(models.Span.status != "ok").label("has_error"),
            )
            .where(*filters)
            .group_by(models.Span.trace_id, models.Span.workflow_type)
            .order_by(func.min(models.Span.start_time).desc())
            .limit(limit).offset(offset)
        )
        rows = await self.session.execute(agg_stmt)
        summaries = [
            TraceSummary(
                trace_id=row.trace_id, tenant_id=tenant_id, workflow_type=row.workflow_type,
                span_count=row.span_count, start_time=_as_utc(row.start_time), end_time=_as_utc(row.end_time),
                has_error=bool(row.has_error),
            )
            for row in rows
        ]
        return summaries, total

    async def list_spans_in_window(
        self, tenant_id: str, *, service_name: str | None, since: datetime,
    ) -> list[SpanRecord]:
        filters = [models.Span.tenant_id == tenant_id, models.Span.start_time >= since]
        if service_name is not None:
            filters.append(models.Span.service_name == service_name)
        rows = await self.session.execute(select(models.Span).where(*filters))
        return [_span_to_domain(m) for m in rows.scalars().all()]

    async def create_slo(self, record: SLODefinition) -> SLODefinition:
        m = models.SLO(
            id=record.id, tenant_id=record.tenant_id, name=record.name, metric=record.metric.value,
            target=record.target, window_hours=record.window_hours, service_name=record.service_name,
            created_at=record.created_at,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _slo_to_domain(m)

    async def get_slo(self, slo_id: str) -> SLODefinition | None:
        m = await self.session.get(models.SLO, slo_id)
        return _slo_to_domain(m) if m else None

    async def list_slos(
        self, *, tenant_id: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[SLODefinition], int]:
        filters = []
        if tenant_id is not None:
            filters.append(models.SLO.tenant_id == tenant_id)
        total = (await self.session.execute(select(func.count(models.SLO.id)).where(*filters))).scalar_one()
        stmt = select(models.SLO).where(*filters).order_by(models.SLO.created_at.desc()).limit(limit).offset(offset)
        rows = await self.session.execute(stmt)
        return [_slo_to_domain(m) for m in rows.scalars().all()], total

    async def create_alert_rule(self, record: AlertRule) -> AlertRule:
        m = models.AlertRule(
            id=record.id, tenant_id=record.tenant_id, name=record.name, metric=record.metric.value,
            comparison=record.comparison.value, threshold=record.threshold, window_hours=record.window_hours,
            service_name=record.service_name, enabled=record.enabled, created_at=record.created_at,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _alert_rule_to_domain(m)

    async def get_alert_rule(self, rule_id: str) -> AlertRule | None:
        m = await self.session.get(models.AlertRule, rule_id)
        return _alert_rule_to_domain(m) if m else None

    async def update_alert_rule(self, record: AlertRule) -> AlertRule:
        m = await self.session.get(models.AlertRule, record.id)
        m.enabled = record.enabled
        await self.session.commit()
        await self.session.refresh(m)
        return _alert_rule_to_domain(m)

    async def list_alert_rules(
        self, *, tenant_id: str | None = None, enabled: bool | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[AlertRule], int]:
        filters = []
        if tenant_id is not None:
            filters.append(models.AlertRule.tenant_id == tenant_id)
        if enabled is not None:
            filters.append(models.AlertRule.enabled == enabled)
        total = (await self.session.execute(select(func.count(models.AlertRule.id)).where(*filters))).scalar_one()
        stmt = (
            select(models.AlertRule).where(*filters).order_by(models.AlertRule.created_at.desc())
            .limit(limit).offset(offset)
        )
        rows = await self.session.execute(stmt)
        return [_alert_rule_to_domain(m) for m in rows.scalars().all()], total

    async def create_alert_event(self, record: AlertEvent) -> AlertEvent:
        m = models.AlertEvent(
            id=record.id, rule_id=record.rule_id, tenant_id=record.tenant_id, status=record.status.value,
            value=record.value, threshold=record.threshold, triggered_at=record.triggered_at,
            resolved_at=record.resolved_at,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _alert_event_to_domain(m)

    async def update_alert_event(self, record: AlertEvent) -> AlertEvent:
        m = await self.session.get(models.AlertEvent, record.id)
        m.status = record.status.value
        m.resolved_at = record.resolved_at
        await self.session.commit()
        await self.session.refresh(m)
        return _alert_event_to_domain(m)

    async def get_latest_alert_event(self, rule_id: str) -> AlertEvent | None:
        stmt = (
            select(models.AlertEvent).where(models.AlertEvent.rule_id == rule_id)
            .order_by(models.AlertEvent.triggered_at.desc()).limit(1)
        )
        m = (await self.session.execute(stmt)).scalar_one_or_none()
        return _alert_event_to_domain(m) if m else None

    async def list_alert_events(
        self, *, tenant_id: str | None = None, status: AlertStatus | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[AlertEvent], int]:
        filters = []
        if tenant_id is not None:
            filters.append(models.AlertEvent.tenant_id == tenant_id)
        if status is not None:
            filters.append(models.AlertEvent.status == status.value)
        total = (await self.session.execute(select(func.count(models.AlertEvent.id)).where(*filters))).scalar_one()
        stmt = (
            select(models.AlertEvent).where(*filters).order_by(models.AlertEvent.triggered_at.desc())
            .limit(limit).offset(offset)
        )
        rows = await self.session.execute(stmt)
        return [_alert_event_to_domain(m) for m in rows.scalars().all()], total
