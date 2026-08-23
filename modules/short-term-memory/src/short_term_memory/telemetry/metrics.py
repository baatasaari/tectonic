"""Prometheus metrics (LLD §Level 4 "Metrics")."""
from __future__ import annotations

from prometheus_client import Counter, Histogram

stm_appends_total = Counter(
    "stm_appends_total",
    "Count of message appends",
    labelnames=("tenant_id",),
)

stm_overflow_events_total = Counter(
    "stm_overflow_events_total",
    "Count of overflow events triggering summarisation",
    labelnames=("tenant_id",),
)

stm_summarisation_duration_seconds = Histogram(
    "stm_summarisation_duration_seconds",
    "Duration of a summarisation call",
    labelnames=("tenant_id",),
)

stm_buffer_token_count = Histogram(
    "stm_buffer_token_count",
    "Distribution of buffer token counts at read time",
    labelnames=("tenant_id",),
)
