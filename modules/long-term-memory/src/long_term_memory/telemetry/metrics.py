"""Prometheus metrics (LLD §Level 4 "Metrics")."""
from __future__ import annotations

from prometheus_client import Counter, Histogram

ltm_items_stored_total = Counter(
    "ltm_items_stored_total",
    "Count of memory items stored",
    labelnames=("tenant_id", "memory_type"),
)

ltm_retrieval_duration_seconds = Histogram(
    "ltm_retrieval_duration_seconds",
    "Duration of a retrieval query",
    labelnames=("tenant_id", "memory_types_queried"),
)

ltm_consolidation_runs_total = Counter(
    "ltm_consolidation_runs_total",
    "Count of consolidation runs",
    labelnames=("tenant_id",),
)

ltm_reflection_entries_total = Counter(
    "ltm_reflection_entries_total",
    "Count of reflection entries created",
    labelnames=("agent_ref",),
)

ltm_erasure_requests_total = Counter(
    "ltm_erasure_requests_total",
    "Count of erasure requests",
    labelnames=("tenant_id", "outcome"),
)

ltm_erasure_completion_duration_seconds = Histogram(
    "ltm_erasure_completion_duration_seconds",
    "Duration of an erasure request's completion",
    labelnames=("tenant_id",),
)
