"""SQLAlchemy-backed implementation of SentinelRepository (LLD §3)."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sentinel_agents.core.domain import (
    AgentBaselineRecord,
    AlertRecord,
    AlertStatus,
    AlertType,
    InterventionRecord,
    InterventionType,
    Severity,
    SwarmCorrelationWindowRecord,
)
from sentinel_agents.db import models


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _baseline_to_domain(m: models.AgentBaseline) -> AgentBaselineRecord:
    return AgentBaselineRecord(
        agent_ref=m.agent_ref, action_type=m.action_type, mean=m.mean, m2=m.m2, sample_count=m.sample_count,
        last_updated_at=_as_utc(m.last_updated_at),
    )


def _alert_to_domain(m: models.Alert) -> AlertRecord:
    return AlertRecord(
        id=str(m.id), tenant_id=m.tenant_id, alert_type=AlertType(m.alert_type), agent_refs=list(m.agent_refs or []),
        severity=Severity(m.severity), description=m.description, status=AlertStatus(m.status),
        detected_at=_as_utc(m.detected_at),
    )


def _intervention_to_domain(m: models.InterventionRecordModel) -> InterventionRecord:
    return InterventionRecord(
        id=str(m.id), alert_id=str(m.alert_id), intervention_type=InterventionType(m.intervention_type),
        target_ref=m.target_ref, outcome=m.outcome, executed_at=_as_utc(m.executed_at),
    )


def _swarm_window_to_domain(m: models.SwarmCorrelationWindowModel) -> SwarmCorrelationWindowRecord:
    return SwarmCorrelationWindowRecord(
        id=str(m.id), tenant_id=m.tenant_id, window_start=_as_utc(m.window_start), window_end=_as_utc(m.window_end),
        agent_refs_involved=list(m.agent_refs_involved or []), correlation_score=m.correlation_score,
        pattern_description=m.pattern_description,
    )


class SQLAlchemySentinelRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_baseline(self, tenant_id: str, agent_ref: str, action_type: str) -> AgentBaselineRecord | None:
        rows = await self.session.execute(
            select(models.AgentBaseline).where(
                models.AgentBaseline.tenant_id == tenant_id, models.AgentBaseline.agent_ref == agent_ref,
                models.AgentBaseline.action_type == action_type,
            )
        )
        m = rows.scalars().first()
        return _baseline_to_domain(m) if m else None

    async def upsert_baseline(self, tenant_id: str, record: AgentBaselineRecord) -> AgentBaselineRecord:
        rows = await self.session.execute(
            select(models.AgentBaseline).where(
                models.AgentBaseline.tenant_id == tenant_id, models.AgentBaseline.agent_ref == record.agent_ref,
                models.AgentBaseline.action_type == record.action_type,
            )
        )
        m = rows.scalars().first()
        if m is None:
            m = models.AgentBaseline(
                tenant_id=tenant_id, agent_ref=record.agent_ref, action_type=record.action_type,
                mean=record.mean, m2=record.m2, sample_count=record.sample_count,
            )
            self.session.add(m)
        else:
            m.mean = record.mean
            m.m2 = record.m2
            m.sample_count = record.sample_count
        await self.session.commit()
        await self.session.refresh(m)
        return _baseline_to_domain(m)

    async def list_baselines_for_agent(self, tenant_id: str, agent_ref: str) -> list[AgentBaselineRecord]:
        # Deliberately NOT limit/offset paginated — see the Protocol docstring in
        # core/ports.py: one row per (tenant_id, agent_ref, action_type), updated in place,
        # so this is bounded by an agent's small, fixed set of distinct action types.
        rows = await self.session.execute(
            select(models.AgentBaseline).where(
                models.AgentBaseline.tenant_id == tenant_id, models.AgentBaseline.agent_ref == agent_ref,
            )
        )
        return [_baseline_to_domain(m) for m in rows.scalars().all()]

    async def create_alert(self, record: AlertRecord) -> AlertRecord:
        m = models.Alert(
            id=record.id, tenant_id=record.tenant_id, alert_type=record.alert_type.value,
            agent_refs=record.agent_refs, severity=record.severity.value, description=record.description,
            status=record.status.value,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _alert_to_domain(m)

    async def get_alert(self, tenant_id: str, alert_id: str) -> AlertRecord | None:
        m = await self.session.get(models.Alert, alert_id)
        if m is None or m.tenant_id != tenant_id:
            return None
        return _alert_to_domain(m)

    async def update_alert(self, record: AlertRecord) -> AlertRecord:
        m = await self.session.get(models.Alert, record.id)
        if m is None:
            raise LookupError(record.id)
        m.status = record.status.value
        await self.session.commit()
        await self.session.refresh(m)
        return _alert_to_domain(m)

    async def list_alerts(
        self, tenant_id: str, severity: str | None = None, *, limit: int = 50, offset: int = 0,
    ) -> tuple[list[AlertRecord], int]:
        filters = [models.Alert.tenant_id == tenant_id]
        if severity:
            filters.append(models.Alert.severity == severity)

        count_stmt = select(func.count(models.Alert.id)).where(*filters)
        total = (await self.session.execute(count_stmt)).scalar_one()

        # Alerts are a genuinely growing history — order by detected_at (newest first is the
        # useful default for an alert feed), with id as a tiebreaker for rows sharing a
        # timestamp, so limit/offset pagination is stable.
        stmt = (
            select(models.Alert)
            .where(*filters)
            .order_by(models.Alert.detected_at.desc(), models.Alert.id.asc())
            .limit(limit)
            .offset(offset)
        )
        rows = await self.session.execute(stmt)
        return [_alert_to_domain(m) for m in rows.scalars().all()], total

    async def create_intervention_record(self, record: InterventionRecord) -> InterventionRecord:
        m = models.InterventionRecordModel(
            id=record.id, alert_id=record.alert_id, intervention_type=record.intervention_type.value,
            target_ref=record.target_ref, outcome=record.outcome,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _intervention_to_domain(m)

    async def create_swarm_window(self, record: SwarmCorrelationWindowRecord) -> SwarmCorrelationWindowRecord:
        m = models.SwarmCorrelationWindowModel(
            id=record.id, tenant_id=record.tenant_id, window_start=record.window_start, window_end=record.window_end,
            agent_refs_involved=record.agent_refs_involved, correlation_score=record.correlation_score,
            pattern_description=record.pattern_description,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _swarm_window_to_domain(m)
