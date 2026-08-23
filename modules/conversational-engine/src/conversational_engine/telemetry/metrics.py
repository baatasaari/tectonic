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
