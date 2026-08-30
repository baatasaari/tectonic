"""Prometheus metrics (LLD §Level 4 "Metrics")."""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

guardrails_checks_total = Counter(
    "guardrails_checks_total",
    "Count of check requests",
    labelnames=("tenant_id", "stage", "decision"),
)

guardrails_check_duration_seconds = Histogram(
    "guardrails_check_duration_seconds",
    "Duration of a check request",
    labelnames=("tenant_id", "stage"),
)

guardrails_intervention_rate = Gauge(
    "guardrails_intervention_rate",
    "Block+redact ratio",
    labelnames=("tenant_id",),
)

guardrails_redteam_bypass_total = Counter(
    "guardrails_redteam_bypass_total",
    "Count of red-team bypasses",
    labelnames=("tenant_id", "attack_pattern"),
)
