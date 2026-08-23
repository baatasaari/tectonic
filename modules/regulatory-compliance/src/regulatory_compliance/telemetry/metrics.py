"""Prometheus metrics (LLD §Level 4 "Metrics")."""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

regcomp_control_events_total = Counter(
    "regcomp_control_events_total",
    "Count of control implementation events recorded",
    labelnames=("tenant_id", "control_name"),
)

regcomp_evidence_packs_generated_total = Counter(
    "regcomp_evidence_packs_generated_total",
    "Count of evidence pack generation attempts",
    labelnames=("tenant_id", "framework_name", "outcome"),
)

regcomp_evidence_generation_duration_seconds = Histogram(
    "regcomp_evidence_generation_duration_seconds",
    "Duration of evidence pack generation",
    labelnames=("framework_name",),
)

regcomp_framework_coverage_percentage = Gauge(
    "regcomp_framework_coverage_percentage",
    "Percentage of required controls with a recorded implementation event",
    labelnames=("tenant_id", "framework_name"),
)
