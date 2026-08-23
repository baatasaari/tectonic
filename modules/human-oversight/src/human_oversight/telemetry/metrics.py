"""Prometheus metrics (LLD §Level 4 "Metrics")."""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

oversight_requests_total = Counter(
    "oversight_requests_total",
    "Count of oversight requests by outcome",
    labelnames=("tenant_id", "requesting_module", "outcome"),
)

oversight_wait_duration_seconds = Histogram(
    "oversight_wait_duration_seconds",
    "Wait duration from creation to decision",
    labelnames=("tenant_id", "priority"),
)

oversight_override_rate = Gauge(
    "oversight_override_rate",
    "Fraction of decisions that were overrides",
    labelnames=("tenant_id", "requesting_module"),
)

oversight_notification_delivery_failures_total = Counter(
    "oversight_notification_delivery_failures_total",
    "Count of notification delivery failures",
    labelnames=("channel",),
)
