"""In-memory fakes for unit tests."""
from __future__ import annotations

from typing import Any

from evaluation_framework.core.domain import (
    DomainMetricPackRecord,
    EvalRunRecord,
    GateResultRecord,
    MetricScoreRecord,
)


class InMemoryEvaluationFrameworkRepository:
    def __init__(self) -> None:
        self.eval_runs: dict[str, EvalRunRecord] = {}
        self.metric_scores: dict[str, MetricScoreRecord] = {}
        self.gate_results: dict[str, GateResultRecord] = {}
        self.domain_packs: dict[str, DomainMetricPackRecord] = {}

    async def create_eval_run(self, record: EvalRunRecord) -> EvalRunRecord:
        self.eval_runs[record.id] = record
        return record

    async def update_eval_run(self, record: EvalRunRecord) -> EvalRunRecord:
        self.eval_runs[record.id] = record
        return record

    async def get_eval_run(self, tenant_id: str, eval_run_id: str) -> EvalRunRecord | None:
        run = self.eval_runs.get(eval_run_id)
        if run is None or run.tenant_id != tenant_id:
            return None
        return run

    async def create_metric_score(self, record: MetricScoreRecord) -> MetricScoreRecord:
        self.metric_scores[record.id] = record
        return record

    async def list_metric_scores_for_run(self, eval_run_id: str) -> list[MetricScoreRecord]:
        return [s for s in self.metric_scores.values() if s.eval_run_id == eval_run_id]

    async def list_metric_scores_for_tenant(
        self, tenant_id: str, *, agent_ref: str | None = None,
    ) -> list[MetricScoreRecord]:
        results = [s for s in self.metric_scores.values() if s.tenant_id == tenant_id]
        if agent_ref is not None:
            results = [s for s in results if s.agent_ref == agent_ref]
        return results

    async def create_gate_result(self, record: GateResultRecord) -> GateResultRecord:
        self.gate_results[record.id] = record
        return record

    async def create_domain_pack(self, record: DomainMetricPackRecord) -> DomainMetricPackRecord:
        self.domain_packs[record.id] = record
        return record

    async def list_domain_packs(self, tenant_id: str) -> list[DomainMetricPackRecord]:
        return [p for p in self.domain_packs.values() if p.tenant_id == tenant_id]


class StubLLMGatewayClient:
    def __init__(self, judged_score: float = 0.8) -> None:
        self.calls: list[dict] = []
        self.judged_score = judged_score

    async def judge(self, agent_output: str, metric_name: str, reference_data: dict[str, Any]) -> float:
        self.calls.append({"agent_output": agent_output, "metric_name": metric_name, "reference_data": reference_data})
        return self.judged_score
