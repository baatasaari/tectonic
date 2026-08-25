"""Prometheus metrics (LLD §Level 4 "Metrics")."""
from __future__ import annotations

from prometheus_client import Counter

deployment_strategy_deployments_total = Counter(
    "deployment_strategy_deployments_total",
    "Count of deployment stage transitions (deployment frequency, change failure rate)",
    labelnames=("stage",),
)

deployment_strategy_rollbacks_total = Counter(
    "deployment_strategy_rollbacks_total",
    "Count of rollbacks (change failure rate's numerator)",
    labelnames=("service_name",),
)

deployment_strategy_canary_health_evaluations_total = Counter(
    "deployment_strategy_canary_health_evaluations_total",
    "Count of canary health check evaluations",
    labelnames=("outcome",),
)
