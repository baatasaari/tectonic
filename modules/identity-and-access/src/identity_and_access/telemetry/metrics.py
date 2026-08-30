"""Prometheus metrics (LLD §Level 4 "Metrics")."""
from __future__ import annotations

from prometheus_client import Counter

identity_access_unauthorized_attempts_total = Counter(
    "identity_access_unauthorized_attempts_total",
    "Count of denied authorize() calls (the LLD's own key metric, wired for real)",
    labelnames=("tenant_id", "required_scope"),
)

identity_access_auth_decisions_total = Counter(
    "identity_access_auth_decisions_total",
    "Count of authorize() decisions (auth success rate = allowed=True / total)",
    labelnames=("allowed",),
)

identity_access_tokens_issued_total = Counter(
    "identity_access_tokens_issued_total",
    "Count of scoped tokens issued",
    labelnames=("tenant_id",),
)
