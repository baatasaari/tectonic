"""Real metric computation over already-fetched span data -- the one
place `SLOService` and `AlertingService` both compute `SLOMetric`
values from, so an SLO and an alert rule watching the same metric over
the same window always agree.

`compute_metric` never fabricates a value: given zero spans it returns
`(None, 0)`, and every caller must treat `None` as "nothing to
evaluate" rather than defaulting to a pass or a fail.
"""
from __future__ import annotations

import math

from observability.core.domain import SLOMetric, SpanRecord


def compute_metric(spans: list[SpanRecord], metric: SLOMetric) -> tuple[float | None, int]:
    """Returns `(value, sample_count)`."""
    if not spans:
        return None, 0

    if metric == SLOMetric.ERROR_RATE:
        errors = sum(1 for s in spans if s.status != "ok")
        return errors / len(spans), len(spans)

    if metric == SLOMetric.LATENCY_P95:
        durations = sorted(s.duration_seconds for s in spans)
        return _percentile(durations, 0.95), len(durations)

    raise ValueError(f"unknown SLO metric: {metric!r}")


def _percentile(sorted_values: list[float], p: float) -> float:
    """Linear-interpolation percentile (the same method NumPy's default
    `percentile` uses) -- real, standard, no external stats dependency
    for a single call site."""
    if len(sorted_values) == 1:
        return sorted_values[0]

    rank = (len(sorted_values) - 1) * p
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return sorted_values[int(rank)]
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * (rank - lower)
