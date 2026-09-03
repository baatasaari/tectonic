"""Abstract ports this module depends on: persistence and LLM Gateway
(LLM-as-judge calls for metrics with no local heuristic)."""
from __future__ import annotations

from typing import Any, Protocol

from evaluation_framework.core.domain import (
    DomainMetricPackRecord,
    EvalRunRecord,
    GateResultRecord,
    MetricScoreRecord,
)


class EvaluationFrameworkRepository(Protocol):
    async def create_eval_run(self, record: EvalRunRecord) -> EvalRunRecord: ...

    async def update_eval_run(self, record: EvalRunRecord) -> EvalRunRecord: ...

    async def get_eval_run(self, tenant_id: str, eval_run_id: str) -> EvalRunRecord | None: ...

    async def create_metric_score(self, record: MetricScoreRecord) -> MetricScoreRecord: ...

    async def list_metric_scores_for_run(self, eval_run_id: str) -> list[MetricScoreRecord]: ...

    async def list_metric_scores_for_tenant(
        self, tenant_id: str, *, agent_ref: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[MetricScoreRecord], int]: ...

    async def list_eval_runs_for_agent_ref(
        self, tenant_id: str, agent_ref: str, *, limit: int = 50, offset: int = 0,
    ) -> tuple[list[EvalRunRecord], int]:
        """Most-recent-first (by `started_at`). Backs `GET /eval-runs` --
        the lookup a release-gating caller (PromptOps' `conclude`, LLMOps'
        `promote`) needs to find the `eval_run_id` its own gate check
        should reference, since neither module tracks that id itself."""
        ...

    async def create_gate_result(self, record: GateResultRecord) -> GateResultRecord: ...

    async def create_domain_pack(self, record: DomainMetricPackRecord) -> DomainMetricPackRecord: ...

    async def list_domain_packs(self, tenant_id: str) -> list[DomainMetricPackRecord]: ...


class LLMGatewayClient(Protocol):
    async def judge(self, agent_output: str, metric_name: str, reference_data: dict[str, Any]) -> float:
        """LLM-as-judge fallback for a metric with no local heuristic implementation.
        Returns a 0.0-1.0 score."""
        ...

    async def complete(self, prompt: str) -> str:
        """Raw text completion — the primitive DeepEval's real metric classes need
        (core/deepeval_adapter.py), since DeepEval's own prompt templates already embed
        the schema/format instructions and just need a text-in/text-out call."""
        ...
