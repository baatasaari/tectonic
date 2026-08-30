"""Gate Engine (LLD §2 sub-components): applies pass/fail thresholds for
CI/CD gating, aggregating the MetricScores already computed for an
EvalRun."""
from __future__ import annotations

from evaluation_framework.core.domain import (
    EvalRunNotFoundError,
    GateResultRecord,
    MetricScoreRecord,
    new_id,
)
from evaluation_framework.core.ports import EvaluationFrameworkRepository


class GateEngine:
    def __init__(self, repository: EvaluationFrameworkRepository) -> None:
        self._repository = repository

    async def gate(self, tenant_id: str, eval_run_id: str, environment: str = "production") -> GateResultRecord:
        run = await self._repository.get_eval_run(tenant_id, eval_run_id)
        if run is None:
            raise EvalRunNotFoundError(eval_run_id)

        scores = await self._repository.list_metric_scores_for_run(eval_run_id)
        blocking = self._blocking_failures(scores)
        result = GateResultRecord(
            id=new_id(), eval_run_id=eval_run_id, overall_passed=not blocking, blocking_failures=blocking,
            environment=environment,
        )
        return await self._repository.create_gate_result(result)

    @staticmethod
    def _blocking_failures(scores: list[MetricScoreRecord]) -> list[str]:
        return [s.metric_name for s in scores if not s.passed]
