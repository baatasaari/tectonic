"""Prometheus metrics (LLD §Level 4 "Metrics")."""
from __future__ import annotations

from prometheus_client import Counter

agent_cards_registered_total = Counter(
    "agent_cards_registered_total",
    "Count of Agent Cards registered",
    labelnames=("tenant_id",),
)

agent_cards_trust_score_computations_total = Counter(
    "agent_cards_trust_score_computations_total",
    "Count of trust score computations",
    labelnames=("outcome",),
)

agent_cards_discovery_requests_total = Counter(
    "agent_cards_discovery_requests_total",
    "Count of discovery (search) requests",
    labelnames=("tenant_id",),
)

# security/entitlement_gate.py's bounded-staleness cache: distinguishes a
# real Multi-tenancy outage's two possible outcomes so both are observable
# (previously invisible under the old unconditional-fail-open posture).
entitlement_gate_stale_served_total = Counter(
    "entitlement_gate_stale_served_total",
    "Count of requests served a stale-but-still-bounded cached entitlement decision "
    "because Multi-tenancy was unreachable",
    labelnames=("module",),
)

entitlement_gate_fail_closed_total = Counter(
    "entitlement_gate_fail_closed_total",
    "Count of requests denied because Multi-tenancy was unreachable and no "
    "recent verified entitlement decision was cached",
    labelnames=("module",),
)
