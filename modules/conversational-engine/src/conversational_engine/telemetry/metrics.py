"""Prometheus metrics (LLD §Level 4 "Metrics")."""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

conversation_turns_total = Counter(
    "conversation_turns_total",
    "Count of conversation turns",
    labelnames=("tenant_id", "channel", "outcome"),  # outcome: completed|refused|error
)

conversation_turn_duration_seconds = Histogram(
    "conversation_turn_duration_seconds",
    "Duration of a full turn",
    labelnames=("tenant_id", "channel"),
)

conversation_time_to_first_token_seconds = Histogram(
    "conversation_time_to_first_token_seconds",
    "Time from turn start to first streamed token",
    labelnames=("tenant_id", "channel"),
    buckets=(0.05, 0.1, 0.15, 0.2, 0.3, 0.5, 1.0, 2.0),
)

conversation_handoff_total = Counter(
    "conversation_handoff_total",
    "Count of handoffs triggered",
    labelnames=("tenant_id", "trigger_reason"),
)

conversation_sessions_active = Gauge(
    "conversation_sessions_active",
    "Number of active conversation sessions",
    labelnames=("tenant_id", "channel"),
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
