"""Reliability Scorer (LLD §2.2, differentiator: "tool reliability scoring
feeding routing decisions"). Computes a rolling reliability score per tool
from invocation history, updated in real time on each invocation — an
exponential moving average rather than a fixed lookback window, so it
adapts smoothly without needing to store a rolling history buffer per tool.
"""
from __future__ import annotations

from tool_orchestration.core.domain import ReliabilityScoreRecord, now
from tool_orchestration.telemetry.metrics import tool_reliability_score

# Weight given to the newest observation. Lower = smoother/slower to react,
# higher = more reactive to a sudden run of failures.
_EMA_ALPHA = 0.2


class ReliabilityScorer:
    def update(self, current: ReliabilityScoreRecord | None, tool_id: str, success: bool, latency_ms: float) -> ReliabilityScoreRecord:
        if current is None:
            current = ReliabilityScoreRecord(tool_id=tool_id)

        observed_success = 1.0 if success else 0.0
        new_success_rate = (1 - _EMA_ALPHA) * current.rolling_success_rate + _EMA_ALPHA * observed_success
        new_avg_latency = (1 - _EMA_ALPHA) * current.rolling_avg_latency_ms + _EMA_ALPHA * latency_ms

        updated = ReliabilityScoreRecord(
            tool_id=tool_id,
            rolling_success_rate=max(0.0, min(1.0, new_success_rate)),
            rolling_avg_latency_ms=max(0.0, new_avg_latency),
            last_updated_at=now(),
        )
        tool_reliability_score.labels(tool_id=tool_id).set(updated.rolling_success_rate)
        return updated
