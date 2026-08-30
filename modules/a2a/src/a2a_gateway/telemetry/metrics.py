"""Prometheus metrics (LLD §Level 4 "Metrics")."""
from __future__ import annotations

from prometheus_client import Counter, Histogram

a2a_tasks_total = Counter(
    "a2a_tasks_total",
    "Count of A2A tasks, either direction",
    labelnames=("direction", "skill_id", "outcome"),
)

a2a_delegation_latency_seconds = Histogram(
    "a2a_delegation_latency_seconds",
    "Latency of outbound delegation calls",
    labelnames=("direction",),
)

a2a_card_fetch_total = Counter(
    "a2a_card_fetch_total",
    "Count of Agent Card fetches (outbound delegation handshake)",
    labelnames=("outcome",),
)
