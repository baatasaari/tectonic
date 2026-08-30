"""SLO Service: define per-tenant service-level objectives over the
two metrics this module can actually compute from ingested span data
(`SLOMetric`), and evaluate one on demand against its own trailing
window. There's no real cron/scheduler infra in this sandbox (the same
constraint every other module's "who calls this periodically" gap
hits) -- `evaluate` is the real, tested computation a real scheduler
(or an operator, or a dashboard) is meant to call; see
`core/alerting_service.py` for the sibling that reconciles a firing/
resolved state machine from the same computation.
"""
from __future__ import annotations

from datetime import timedelta

from observability.core.domain import (
    SLODefinition,
    SLOEvaluationResult,
    SLOMetric,
    SLONotFoundError,
    new_id,
    now,
)
from observability.core.metrics_query import compute_metric
from observability.core.ports import ObservabilityRepository


class SLOService:
    def __init__(self, repository: ObservabilityRepository) -> None:
        self._repository = repository

    async def create(
        self, *, tenant_id: str, name: str, metric: SLOMetric, target: float, window_hours: int,
        service_name: str | None = None,
    ) -> SLODefinition:
        slo = SLODefinition(
            id=new_id(), tenant_id=tenant_id, name=name, metric=metric, target=target, window_hours=window_hours,
            service_name=service_name,
        )
        return await self._repository.create_slo(slo)

    async def get(self, slo_id: str) -> SLODefinition:
        slo = await self._repository.get_slo(slo_id)
        if slo is None:
            raise SLONotFoundError(slo_id)
        return slo

    async def list(
        self, *, tenant_id: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[SLODefinition], int]:
        return await self._repository.list_slos(tenant_id=tenant_id, limit=limit, offset=offset)

    async def evaluate(self, slo_id: str) -> SLOEvaluationResult:
        slo = await self.get(slo_id)
        since = now() - timedelta(hours=slo.window_hours)
        spans = await self._repository.list_spans_in_window(slo.tenant_id, service_name=slo.service_name, since=since)
        value, count = compute_metric(spans, slo.metric)

        if value is None:
            # Zero samples in the window -- nothing to be compliant or non-compliant
            # about, the same insufficient-data-over-fabrication call this platform's
            # other compliance-rate computations already make.
            return SLOEvaluationResult(
                slo_id=slo.id, tenant_id=slo.tenant_id, metric=slo.metric, target=slo.target, sample_count=0,
                current_value=None, compliant=None, error_budget_remaining=None,
            )

        # Both metrics this module computes are "lower is better, target is a
        # ceiling": error_rate must not exceed its target fraction, and p95 latency
        # must not exceed its target seconds.
        compliant = value <= slo.target
        error_budget_remaining = None
        if slo.metric == SLOMetric.ERROR_RATE and slo.target > 0:
            error_budget_remaining = (slo.target - value) / slo.target

        return SLOEvaluationResult(
            slo_id=slo.id, tenant_id=slo.tenant_id, metric=slo.metric, target=slo.target, sample_count=count,
            current_value=value, compliant=compliant, error_budget_remaining=error_budget_remaining,
        )
