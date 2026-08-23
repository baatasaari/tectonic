"""Prometheus metrics (LLD §4.3)."""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

workflow_steps_total = Counter(
    "workflow_steps_total",
    "Count of workflow step executions",
    labelnames=("tenant_id", "execution_mode", "status"),
)

workflow_step_duration_seconds = Histogram(
    "workflow_step_duration_seconds",
    "Duration of a single step execution",
    labelnames=("tenant_id", "execution_mode"),
)

workflow_orchestration_overhead_seconds = Histogram(
    "workflow_orchestration_overhead_seconds",
    "Scheduler time excluding downstream call time, validated against the sub-50ms target",
    labelnames=("tenant_id",),
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 1.0),
)

workflow_instances_active = Gauge(
    "workflow_instances_active",
    "Number of active workflow instances",
    labelnames=("tenant_id", "status"),
)

workflow_approval_wait_seconds = Histogram(
    "workflow_approval_wait_seconds",
    "Time an instance spent paused for human approval",
    labelnames=("tenant_id",),
)

workflow_replan_total = Counter(
    "workflow_replan_total",
    "Count of replan attempts",
    labelnames=("tenant_id", "trigger_reason", "outcome"),
)

workflow_event_publish_failures_total = Counter(
    "workflow_event_publish_failures_total",
    "Count of failures publishing lifecycle events to a downstream destination",
    labelnames=("tenant_id", "destination"),
)
