"""Canary Evaluation Service (LLD §2 sub-components, §Level 3 "The
rollout state machine"): reads Evaluation Framework's own real scores
for a model version and renders a gate verdict against configured
thresholds. Never passes on a timer or on volume alone: a sample size
below `min_canary_sample_size` is `insufficient_data`, not a pass.
"""
from __future__ import annotations

from llmops.core.domain import CanaryGateResult, ModelVersionRecord
from llmops.core.ports import EvaluationFrameworkClient


def evaluation_ref(model_version: ModelVersionRecord) -> str:
    """The `agent_ref` a model version's own evaluation runs must be
    tagged with for this gate to find them -- distinct from
    `artifact_ref` (a provider-specific identifier), so evaluation
    attribution doesn't depend on knowing that internal detail."""
    return f"model:{model_version.model_name}:{model_version.version}"


class CanaryEvaluationService:
    def __init__(
        self, evaluation_framework: EvaluationFrameworkClient, *,
        min_sample_size: int = 10, min_pass_rate: float = 0.95,
    ) -> None:
        self._evaluation_framework = evaluation_framework
        self._min_sample_size = min_sample_size
        self._min_pass_rate = min_pass_rate

    async def evaluate(self, model_version: ModelVersionRecord) -> CanaryGateResult:
        scores = await self._evaluation_framework.list_scores(
            tenant_id=model_version.tenant_id, agent_ref=evaluation_ref(model_version),
        )
        sample_size = len(scores)

        if sample_size < self._min_sample_size:
            return CanaryGateResult(
                sample_size=sample_size, pass_rate=None, passed=False,
                reason=f"insufficient_data: {sample_size}/{self._min_sample_size} required samples",
            )

        pass_rate = sum(1 for s in scores if s.get("passed")) / sample_size
        if pass_rate < self._min_pass_rate:
            return CanaryGateResult(
                sample_size=sample_size, pass_rate=pass_rate, passed=False,
                reason=f"pass_rate {pass_rate:.2%} below required {self._min_pass_rate:.2%}",
            )

        return CanaryGateResult(sample_size=sample_size, pass_rate=pass_rate, passed=True, reason="passed")
