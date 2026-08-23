"""Prometheus metrics (LLD §Level 4 "Metrics")."""
from __future__ import annotations

from prometheus_client import Counter, Histogram

context_assemblies_total = Counter(
    "context_assemblies_total",
    "Count of context assembly requests",
    labelnames=("tenant_id", "task_type"),
)

context_token_utilisation_ratio = Histogram(
    "context_token_utilisation_ratio",
    "tokens_used / token_budget",
    labelnames=("tenant_id", "task_type"),
)

context_truncation_rate = Histogram(
    "context_truncation_rate",
    "items_dropped / items_candidate",
    labelnames=("tenant_id", "task_type"),
)

context_assembly_duration_seconds = Histogram(
    "context_assembly_duration_seconds",
    "Duration of an assembly request",
    labelnames=("tenant_id",),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)

context_summarisation_invocations_total = Counter(
    "context_summarisation_invocations_total",
    "Count of summarisation calls",
    labelnames=("tenant_id",),
)
