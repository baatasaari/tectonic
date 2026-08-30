"""Canary Health Calculator (LLD §2 sub-components, §Level 3 "Canary
Health Calculator"): a weighted combination of two real platform-peer
signals -- Evaluation Framework's own per-deployment groundedness pass
rate, and FinOps's own per-tenant budget utilisation -- with graceful
degradation when either (or both) peer has no data yet. Reuses Agent
Cards (Module 23)'s own weighted-renormalization-over-available-signals
math, applied here to a promotion gate instead of a trust score. Never
fabricates a neutral placeholder: a signal with no data is excluded, not
defaulted to some assumed-healthy number, and zero signals with data is
`insufficient_data` -- never a default pass.
"""
from __future__ import annotations

from collections.abc import Awaitable
from typing import TypeVar

from deployment_strategy.core.domain import CanaryHealthResult, DeploymentRecord
from deployment_strategy.core.ports import EvaluationFrameworkClient, FinOpsClient
from deployment_strategy.telemetry.logging import get_logger

logger = get_logger(component="canary_health_calculator")

T = TypeVar("T")


def deployment_ref(deployment: DeploymentRecord) -> str:
    """The `agent_ref` a deployment's own evaluation runs must be tagged
    with for this gate to find them -- distinct from `build_ref` (an
    image tag / artefact digest), so evaluation attribution doesn't
    depend on knowing that internal detail. The same dedicated-
    attribution-convention shape LLMOps (Module 25)'s own
    `evaluation_ref` already established."""
    return f"deployment:{deployment.service_name}:{deployment.build_ref}"


def _groundedness_score(scores: list[dict], min_sample_size: int) -> float | None:
    if len(scores) < min_sample_size:
        return None
    return sum(1 for s in scores if s.get("passed")) / len(scores)


def _cost_score(utilisation_ratio: float | None) -> float | None:
    if utilisation_ratio is None:
        return None
    return max(0.0, 1.0 - min(utilisation_ratio, 1.0))


def _weighted_composite(
    *, groundedness_score: float | None, cost_score: float | None,
    groundedness_weight: float, cost_weight: float,
) -> float | None:
    available = [
        (score, weight) for score, weight in
        [(groundedness_score, groundedness_weight), (cost_score, cost_weight)]
        if score is not None
    ]
    if not available:
        return None

    total_weight = sum(weight for _, weight in available)
    if total_weight <= 0:
        # Data exists but every available signal's configured weight is zero (or
        # negative) -- fall back to an unweighted mean rather than reporting "no score".
        return sum(score for score, _ in available) / len(available)
    return sum(score * weight for score, weight in available) / total_weight


class CanaryHealthCalculator:
    def __init__(
        self, evaluation_framework: EvaluationFrameworkClient, finops: FinOpsClient, *,
        min_groundedness_sample_size: int = 10, min_health_score: float = 0.8,
        groundedness_weight: float = 0.6, cost_weight: float = 0.4, budget_period: str = "monthly",
    ) -> None:
        self._evaluation_framework = evaluation_framework
        self._finops = finops
        self._min_groundedness_sample_size = min_groundedness_sample_size
        self._min_health_score = min_health_score
        self._groundedness_weight = groundedness_weight
        self._cost_weight = cost_weight
        self._budget_period = budget_period

    @staticmethod
    async def _safe_call(call: Awaitable[T], *, default: T) -> T:
        try:
            return await call
        except Exception as exc:
            logger.warning("canary_health_signal_unavailable", error=str(exc))
            return default

    async def evaluate(self, deployment: DeploymentRecord) -> CanaryHealthResult:
        # Each peer is queried independently, and a failure on one side never blocks the
        # other: a FinOps outage still leaves a groundedness-only verdict computable,
        # rather than failing the whole health check over one unavailable signal.
        scores = await self._safe_call(
            self._evaluation_framework.list_scores(tenant_id=deployment.tenant_id, agent_ref=deployment_ref(deployment)),
            default=[],
        )
        groundedness_score = _groundedness_score(scores, self._min_groundedness_sample_size)

        utilisation_ratio = None
        if deployment.budget_policy_id:
            utilisation_ratio = await self._safe_call(
                self._finops.cost_report_utilisation(
                    tenant_id=deployment.tenant_id, period=self._budget_period,
                    budget_policy_id=deployment.budget_policy_id,
                ),
                default=None,
            )
        cost_score = _cost_score(utilisation_ratio)

        composite_score = _weighted_composite(
            groundedness_score=groundedness_score, cost_score=cost_score,
            groundedness_weight=self._groundedness_weight, cost_weight=self._cost_weight,
        )

        if composite_score is None:
            return CanaryHealthResult(
                groundedness_score=None, cost_score=None, composite_score=None, passed=False,
                reason="insufficient_data: no health signal has data yet",
            )

        passed = composite_score >= self._min_health_score
        reason = (
            "passed" if passed
            else f"composite health score {composite_score:.2f} below required {self._min_health_score:.2f}"
        )
        return CanaryHealthResult(
            groundedness_score=groundedness_score, cost_score=cost_score, composite_score=composite_score,
            passed=passed, reason=reason,
        )
