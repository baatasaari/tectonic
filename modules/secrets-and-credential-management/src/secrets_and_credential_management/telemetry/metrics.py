"""Prometheus metrics (LLD §Level 4 "Metrics")."""
from __future__ import annotations

from prometheus_client import Counter, Gauge

secrets_access_total = Counter(
    "secrets_access_total",
    "Count of secret retrieval attempts (secret access audit completeness's raw signal)",
    labelnames=("allowed",),
)

secrets_rotations_total = Counter(
    "secrets_rotations_total",
    "Count of secret rotations",
    labelnames=("tenant_id",),
)

secrets_rotation_compliance_rate = Gauge(
    "secrets_rotation_compliance_rate",
    "Fraction of active secrets not currently overdue for rotation (the LLD's own key metric)",
    labelnames=("tenant_id",),
)
