"""Prometheus metrics (LLD §Level 4 "Metrics")."""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

sentinel_alerts_total = Counter(
    "sentinel_alerts_total",
    "Count of alerts raised",
    labelnames=("tenant_id", "alert_type", "severity"),
)

sentinel_interventions_total = Counter(
    "sentinel_interventions_total",
    "Count of interventions executed",
    labelnames=("tenant_id", "intervention_type"),
)

sentinel_detection_latency_seconds = Histogram(
    "sentinel_detection_latency_seconds",
    "Latency from event to alert",
    labelnames=("tenant_id", "alert_type"),
)

sentinel_false_positive_rate = Gauge(
    "sentinel_false_positive_rate",
    "Fraction of alerts dismissed as false positive",
    labelnames=("tenant_id",),
)
