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
