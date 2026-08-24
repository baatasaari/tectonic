"""SQLAlchemy-backed implementation of EvaluationFrameworkRepository
(LLD §3)."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from evaluation_framework.core.domain import (
    DomainMetricPackRecord,
    EvalRunRecord,
    EvalRunStatus,
    GateResultRecord,
    MetricScoreRecord,
)
from evaluation_framework.db import models


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _run_to_domain(m: models.EvalRun) -> EvalRunRecord:
    return EvalRunRecord(
        id=str(m.id), tenant_id=m.tenant_id, trigger_source=m.trigger_source, agent_ref=m.agent_ref,
        metrics_evaluated=list(m.metrics_evaluated or []), status=EvalRunStatus(m.status),
        started_at=_as_utc(m.started_at), completed_at=_as_utc(m.completed_at),
    )


def _score_to_domain(m: models.MetricScore) -> MetricScoreRecord:
    return MetricScoreRecord(
        id=str(m.id), eval_run_id=str(m.eval_run_id), tenant_id=m.tenant_id, agent_ref=m.agent_ref,
        metric_name=m.metric_name, score=m.score, threshold=m.threshold, passed=m.passed,
        created_at=_as_utc(m.created_at),
    )


def _gate_to_domain(m: models.GateResult) -> GateResultRecord:
    return GateResultRecord(
        id=str(m.id), eval_run_id=str(m.eval_run_id), overall_passed=m.overall_passed,
        blocking_failures=list(m.blocking_failures or []), environment=m.environment,
        created_at=_as_utc(m.created_at),
    )


def _pack_to_domain(m: models.DomainMetricPack) -> DomainMetricPackRecord:
    return DomainMetricPackRecord(
        id=str(m.id), tenant_id=m.tenant_id, pack_name=m.pack_name, enabled=m.enabled,
        custom_thresholds=dict(m.custom_thresholds or {}),
    )


class SQLAlchemyEvaluationFrameworkRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_eval_run(self, record: EvalRunRecord) -> EvalRunRecord:
        m = models.EvalRun(
            id=record.id, tenant_id=record.tenant_id, trigger_source=record.trigger_source,
            agent_ref=record.agent_ref, metrics_evaluated=record.metrics_evaluated, status=record.status.value,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _run_to_domain(m)

    async def update_eval_run(self, record: EvalRunRecord) -> EvalRunRecord:
        m = await self.session.get(models.EvalRun, record.id)
        if m is None:
            raise ValueError(f"eval run not found: {record.id}")
        m.status = record.status.value
        m.completed_at = record.completed_at
        await self.session.commit()
        await self.session.refresh(m)
        return _run_to_domain(m)

    async def get_eval_run(self, tenant_id: str, eval_run_id: str) -> EvalRunRecord | None:
        m = await self.session.get(models.EvalRun, eval_run_id)
        if m is None or m.tenant_id != tenant_id:
            return None
        return _run_to_domain(m)

    async def create_metric_score(self, record: MetricScoreRecord) -> MetricScoreRecord:
        m = models.MetricScore(
            id=record.id, eval_run_id=record.eval_run_id, tenant_id=record.tenant_id, agent_ref=record.agent_ref,
            metric_name=record.metric_name, score=record.score, threshold=record.threshold, passed=record.passed,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _score_to_domain(m)

    async def list_metric_scores_for_run(self, eval_run_id: str) -> list[MetricScoreRecord]:
        rows = await self.session.execute(select(models.MetricScore).where(models.MetricScore.eval_run_id == eval_run_id))
        return [_score_to_domain(m) for m in rows.scalars().all()]

    async def list_metric_scores_for_tenant(
        self, tenant_id: str, *, agent_ref: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[MetricScoreRecord], int]:
        stmt = select(models.MetricScore).where(models.MetricScore.tenant_id == tenant_id)
        count_stmt = select(func.count(models.MetricScore.id)).where(models.MetricScore.tenant_id == tenant_id)
        if agent_ref is not None:
            stmt = stmt.where(models.MetricScore.agent_ref == agent_ref)
            count_stmt = count_stmt.where(models.MetricScore.agent_ref == agent_ref)
        stmt = stmt.order_by(models.MetricScore.created_at.desc()).limit(limit).offset(offset)
        rows = await self.session.execute(stmt)
        total = await self.session.execute(count_stmt)
        return [_score_to_domain(m) for m in rows.scalars().all()], total.scalar_one()

    async def create_gate_result(self, record: GateResultRecord) -> GateResultRecord:
        m = models.GateResult(
            id=record.id, eval_run_id=record.eval_run_id, overall_passed=record.overall_passed,
            blocking_failures=record.blocking_failures, environment=record.environment,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _gate_to_domain(m)

    async def create_domain_pack(self, record: DomainMetricPackRecord) -> DomainMetricPackRecord:
        m = models.DomainMetricPack(
            id=record.id, tenant_id=record.tenant_id, pack_name=record.pack_name, enabled=record.enabled,
            custom_thresholds=record.custom_thresholds,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _pack_to_domain(m)

    async def list_domain_packs(self, tenant_id: str) -> list[DomainMetricPackRecord]:
        rows = await self.session.execute(select(models.DomainMetricPack).where(models.DomainMetricPack.tenant_id == tenant_id))
        return [_pack_to_domain(m) for m in rows.scalars().all()]
