"""Prometheus metrics (LLD §Level 4 "Metrics")."""
from __future__ import annotations

from prometheus_client import Counter, Gauge

sdk_portal_developers_registered_total = Counter(
    "sdk_portal_developers_registered_total",
    "Count of developer accounts registered",
)

sdk_portal_sdk_generations_total = Counter(
    "sdk_portal_sdk_generations_total",
    "Count of SDK generation attempts",
    labelnames=("outcome",),
)

sdk_portal_adoption_rate = Gauge(
    "sdk_portal_adoption_rate",
    "Fraction of registered developers with at least one recorded real call (the LLD's own key metric)",
)
