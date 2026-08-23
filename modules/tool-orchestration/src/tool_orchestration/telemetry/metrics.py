"""Prometheus metrics (LLD §Level 4 "Metrics")."""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

tool_invocations_total = Counter(
    "tool_invocations_total",
    "Count of tool invocations",
    labelnames=("tenant_id", "tool_id", "outcome"),
)

tool_invocation_duration_seconds = Histogram(
    "tool_invocation_duration_seconds",
    "Duration of a tool invocation",
    labelnames=("tool_id",),
)

tool_retries_total = Counter(
    "tool_retries_total",
    "Count of retry attempts",
    labelnames=("tool_id",),
)

tool_circuit_breaker_state = Gauge(
    "tool_circuit_breaker_state",
    "0=closed, 1=half_open, 2=open",
    labelnames=("tool_id",),
)

tool_reliability_score = Gauge(
    "tool_reliability_score",
    "Rolling success rate per tool",
    labelnames=("tool_id",),
)

tool_synthesis_requests_total = Counter(
    "tool_synthesis_requests_total",
    "Count of tool synthesis requests",
    labelnames=("tenant_id", "outcome"),  # outcome: approved|rejected|pending_review
)

tool_dispatch_overhead_seconds = Histogram(
    "tool_dispatch_overhead_seconds",
    "Orchestration overhead excluding actual tool execution time",
    buckets=(0.001, 0.005, 0.01, 0.02, 0.05, 0.1),
)
