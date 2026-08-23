"""Swarm Correlation Engine (LLD §2 sub-components): detects cross-agent
emergent anomalies — co-occurring *moderate* deviations across several
distinct agents within a time window, individually below the single-
agent alert threshold but notable in aggregate.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

# A "moderate" deviation is one clearing this z-score floor — below any
# sensitivity tier's single-agent alert threshold (2.0-4.0), but still an
# above-baseline signal worth tracking for cross-agent correlation.
MODERATE_Z_THRESHOLD = 1.5


@dataclass
class ModerateDeviationEvent:
    agent_ref: str
    action_type: str
    z_score: float
    timestamp: datetime


@dataclass
class SwarmDetectionResult:
    agent_refs: list[str]
    correlation_score: float
    pattern_description: str
    window_start: datetime
    window_end: datetime


def detect(
    events: list[ModerateDeviationEvent], *, window_seconds: int, min_agents: int, reference_time: datetime,
) -> SwarmDetectionResult | None:
    window_start = reference_time - timedelta(seconds=window_seconds)
    in_window = [e for e in events if window_start <= e.timestamp <= reference_time]
    if not in_window:
        return None

    distinct_agents = sorted({e.agent_ref for e in in_window})
    if len(distinct_agents) < min_agents:
        return None

    avg_z = sum(e.z_score for e in in_window) / len(in_window)
    return SwarmDetectionResult(
        agent_refs=distinct_agents, correlation_score=avg_z,
        pattern_description=f"{len(distinct_agents)} agents showed correlated deviation within {window_seconds}s",
        window_start=window_start, window_end=reference_time,
    )


def prune_older_than(events: list[ModerateDeviationEvent], reference_time: datetime, window_seconds: int) -> list[ModerateDeviationEvent]:
    cutoff = reference_time - timedelta(seconds=window_seconds)
    return [e for e in events if e.timestamp >= cutoff]


class SwarmWindowTracker:
    """Holds the sliding window of recent moderate-deviation events. Must
    be a single long-lived instance shared across requests (constructed
    once in AppContext) — a fresh instance per request would never
    accumulate enough history to correlate anything. See
    `core/event_processor.py`'s module docstring for the corresponding
    multi-replica caveat.
    """

    def __init__(self) -> None:
        self._events: list[ModerateDeviationEvent] = []

    def record(self, event: ModerateDeviationEvent) -> None:
        self._events.append(event)

    def prune(self, reference_time: datetime, window_seconds: int) -> None:
        self._events = prune_older_than(self._events, reference_time, window_seconds)

    def detect(self, *, window_seconds: int, min_agents: int, reference_time: datetime) -> SwarmDetectionResult | None:
        return detect(self._events, window_seconds=window_seconds, min_agents=min_agents, reference_time=reference_time)
