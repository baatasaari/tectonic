"""Prometheus metrics (LLD §Level 4 "Metrics")."""
from __future__ import annotations

from prometheus_client import Counter

multi_tenancy_isolation_breach_incidents_total = Counter(
    "multi_tenancy_isolation_breach_incidents_total",
    "Count of foreign records found by isolation probes (the LLD's own key metric, "
    "target zero) -- incremented by the actual breach count found, not once per probe",
    labelnames=("target_name",),
)

multi_tenancy_isolation_probes_total = Counter(
    "multi_tenancy_isolation_probes_total",
    "Count of isolation probe runs",
    labelnames=("target_name", "passed"),
)

multi_tenancy_tenants_total = Counter(
    "multi_tenancy_tenants_total",
    "Count of tenant lifecycle transitions",
    labelnames=("status",),
)
