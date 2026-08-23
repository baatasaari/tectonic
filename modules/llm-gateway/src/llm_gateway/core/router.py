"""Quality-Aware Router (LLD §2.2, differentiator: "quality-aware routing,
not just cost/latency routing"). Produces an ordered candidate list —
provider names, best first — for the Failover Manager to walk through.

Cost and latency per provider aren't in the LLD's data model as separate
tracked fields, so this uses each ProviderConfig's `priority` (lower is
better) as a shared proxy for both, normalized against the candidate set,
combined with the live quality score from the Evaluation Framework feed
(via QualityScoreProvider) per the configured strategy weights. This keeps
the algorithm's shape faithful to the LLD ("custom scoring function, weights
configurable") without inventing cost/latency telemetry the data model
doesn't carry.
"""
from __future__ import annotations

from dataclasses import dataclass

from llm_gateway.config import RoutingConfig
from llm_gateway.core.domain import ProviderConfigRecord
from llm_gateway.core.ports import QualityScoreProvider

_STRATEGY_WEIGHT_OVERRIDE: dict[str, tuple[float, float, float]] = {
    # (quality, cost, latency) — cost/latency-optimised strategies ignore
    # quality entirely rather than blend it in, matching their name.
    "cost_optimised": (0.0, 1.0, 0.0),
    "latency_optimised": (0.0, 0.0, 1.0),
}


@dataclass
class ScoredCandidate:
    provider: str
    score: float


class QualityAwareRouter:
    def __init__(self, quality_scores: QualityScoreProvider, config: RoutingConfig) -> None:
        self.quality_scores = quality_scores
        self.config = config

    async def rank_candidates(
        self,
        providers: list[ProviderConfigRecord],
        *,
        model: str,
        task_type: str,
        allowed_provider_names: list[str] | None,
        priority_override: list[str],
    ) -> list[str]:
        eligible = [
            p
            for p in providers
            if p.health_status != "down"
            and (not allowed_provider_names or p.provider_name in allowed_provider_names)
        ]
        if not eligible:
            return []

        # An explicit per-tenant provider priority order wins outright for
        # any provider it names; anything else falls through to scoring.
        ordered: list[str] = [name for name in priority_override if name in {p.provider_name for p in eligible}]
        remaining = [p for p in eligible if p.provider_name not in ordered]
        if not remaining:
            return ordered

        quality_w, cost_w, latency_w = _STRATEGY_WEIGHT_OVERRIDE.get(
            self.config.strategy, (self.config.quality_weight, self.config.cost_weight, self.config.latency_weight)
        )

        max_priority = max((p.priority for p in remaining), default=1) or 1
        scored: list[ScoredCandidate] = []
        for p in remaining:
            quality = await self.quality_scores.get_score(p.provider_name, model, task_type)
            # priority 0 is best; normalize to a 0..1 "goodness" score.
            priority_goodness = 1.0 - (p.priority / max_priority)
            degraded_penalty = 0.5 if p.health_status == "degraded" else 1.0
            score = (quality_w * quality + cost_w * priority_goodness + latency_w * priority_goodness) * degraded_penalty
            scored.append(ScoredCandidate(provider=p.provider_name, score=score))

        scored.sort(key=lambda c: c.score, reverse=True)
        return ordered + [c.provider for c in scored]
