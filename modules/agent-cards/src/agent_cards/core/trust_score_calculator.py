"""Trust Score Calculator (LLD §2 sub-components, §Level 3 "Trust score
computation"): a weighted combination of two real platform-peer signals
-- Evaluation Framework's own per-agent metric-score history, and
Regulatory Compliance's own per-tenant control-coverage percentage --
with graceful degradation when either (or both) peer has no data yet.
Never fabricates a neutral placeholder score: a component with no data
is excluded, not defaulted to 0.5.
"""
from __future__ import annotations

from collections.abc import Awaitable
from typing import TypeVar

from agent_cards.core.domain import AgentCardRecord, TrustScoreBreakdown, now
from agent_cards.core.ports import (
    AgentCardsRepository,
    EvaluationFrameworkClient,
    RegulatoryComplianceClient,
)
from agent_cards.telemetry.logging import get_logger

logger = get_logger(component="trust_score_calculator")

T = TypeVar("T")


def _performance_score(scores: list[dict]) -> float | None:
    if not scores:
        return None
    normalized = []
    for s in scores:
        score, threshold = s.get("score", 0.0), s.get("threshold", 0.0)
        normalized.append(min(score / threshold, 1.0) if threshold > 0 else min(max(score, 0.0), 1.0))
    return sum(normalized) / len(normalized)


def _compliance_score(coverage_percentage: float | None) -> float | None:
    if coverage_percentage is None:
        return None
    return min(max(coverage_percentage / 100.0, 0.0), 1.0)


def _weighted_trust_score(
    *, performance_score: float | None, compliance_score: float | None,
    performance_weight: float, compliance_weight: float,
) -> float | None:
    available = [
        (score, weight) for score, weight in
        [(performance_score, performance_weight), (compliance_score, compliance_weight)]
        if score is not None
    ]
    if not available:
        return None

    total_weight = sum(weight for _, weight in available)
    if total_weight <= 0:
        # Data exists but every available component's configured weight is zero (or
        # negative) -- fall back to an unweighted mean rather than reporting "no score".
        return sum(score for score, _ in available) / len(available)
    return sum(score * weight for score, weight in available) / total_weight


class TrustScoreCalculator:
    def __init__(
        self, repository: AgentCardsRepository, evaluation_framework: EvaluationFrameworkClient,
        regulatory_compliance: RegulatoryComplianceClient, *,
        performance_weight: float = 0.6, compliance_weight: float = 0.4, compliance_framework_name: str = "eu_ai_act",
    ) -> None:
        self._repository = repository
        self._evaluation_framework = evaluation_framework
        self._regulatory_compliance = regulatory_compliance
        self._performance_weight = performance_weight
        self._compliance_weight = compliance_weight
        self._compliance_framework_name = compliance_framework_name

    @staticmethod
    async def _safe_call(call: Awaitable[T], *, default: T) -> T:
        try:
            return await call
        except Exception as exc:
            logger.warning("trust_score_signal_unavailable", error=str(exc))
            return default

    async def recompute(self, card: AgentCardRecord) -> TrustScoreBreakdown:
        # Each peer is queried independently, and a failure on one side never blocks the
        # other: a compliance peer that's down (retries/circuit breaker exhausted) still
        # leaves a performance-only trust score computable, rather than failing the whole
        # recompute over one unavailable signal.
        scores = await self._safe_call(
            self._evaluation_framework.list_scores(tenant_id=card.tenant_id, agent_ref=card.agent_ref), default=[],
        )
        coverage = await self._safe_call(
            self._regulatory_compliance.coverage(tenant_id=card.tenant_id, framework_name=self._compliance_framework_name),
            default=None,
        )

        performance_score = _performance_score(scores)
        compliance_score = _compliance_score(coverage)
        trust_score = _weighted_trust_score(
            performance_score=performance_score, compliance_score=compliance_score,
            performance_weight=self._performance_weight, compliance_weight=self._compliance_weight,
        )

        card.trust_score = trust_score
        card.trust_score_computed_at = now()
        await self._repository.update_card(card)

        return TrustScoreBreakdown(
            performance_score=performance_score, compliance_score=compliance_score, trust_score=trust_score,
        )
