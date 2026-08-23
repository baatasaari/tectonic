"""Evaluator (LLD §Level 3 "Sequence: CI/CD gate before deployment" and
"...continuous production sampling"): runs a metric set against an agent
output, persisting an EvalRun and its MetricScores.
"""
from __future__ import annotations

from typing import Any

from evaluation_framework.core.domain import (
    EvalRunRecord,
    EvalRunStatus,
    MetricScoreRecord,
    new_id,
    now,
)
from evaluation_framework.core.metric_adapters import resolve_metric
from evaluation_framework.core.ports import EvaluationFrameworkRepository, LLMGatewayClient
from evaluation_framework.telemetry.logging import get_logger

logger = get_logger(component="evaluator")


class Evaluator:
    def __init__(
        self, repository: EvaluationFrameworkRepository, llm_gateway: LLMGatewayClient,
        thresholds: dict[str, float],
    ) -> None:
        self._repository = repository
        self._llm_gateway = llm_gateway
        self._thresholds = thresholds

    async def evaluate(
        self, tenant_id: str, agent_ref: str, agent_output: str, reference_data: dict[str, Any] | None,
        metric_set: list[str], trigger_source: str, *, custom_thresholds: dict[str, float] | None = None,
    ) -> tuple[EvalRunRecord, list[MetricScoreRecord]]:
        run = EvalRunRecord(
            id=new_id(), tenant_id=tenant_id, trigger_source=trigger_source, agent_ref=agent_ref,
            metrics_evaluated=metric_set,
        )
        run = await self._repository.create_eval_run(run)

        thresholds = {**self._thresholds, **(custom_thresholds or {})}
        scores: list[MetricScoreRecord] = []
        try:
            for metric_name in metric_set:
                metric = resolve_metric(metric_name)
                score_value = await metric.compute(agent_output, reference_data or {}, self._llm_gateway)
                threshold = thresholds.get(metric_name, 0.7)
                record = MetricScoreRecord(
                    id=new_id(), eval_run_id=run.id, tenant_id=tenant_id, agent_ref=agent_ref,
                    metric_name=metric_name, score=score_value, threshold=threshold, passed=score_value >= threshold,
                )
                record = await self._repository.create_metric_score(record)
                scores.append(record)
            run.status = EvalRunStatus.COMPLETED
        except Exception:
            run.status = EvalRunStatus.FAILED_TO_EVALUATE
            logger.exception("eval_run_failed", eval_run_id=run.id)
        finally:
            run.completed_at = now()
            run = await self._repository.update_eval_run(run)

        return run, scores
