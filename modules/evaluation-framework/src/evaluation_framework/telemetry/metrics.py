"""Prometheus metrics (LLD §Level 4 "Metrics")."""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

eval_runs_total = Counter(
    "eval_runs_total",
    "Count of evaluation runs",
    labelnames=("tenant_id", "trigger_source"),
)

eval_metric_score = Histogram(
    "eval_metric_score",
    "Distribution of metric scores",
    labelnames=("tenant_id", "metric_name"),
)

eval_gate_pass_rate = Gauge(
    "eval_gate_pass_rate",
    "Gate pass rate",
    labelnames=("tenant_id", "environment"),
)

eval_sampling_rate = Gauge(
    "eval_sampling_rate",
    "Actual observed sampling rate vs configured",
    labelnames=("tenant_id",),
)
