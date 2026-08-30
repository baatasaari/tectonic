"""Prometheus metrics (LLD §Level 4 "Metrics")."""
from __future__ import annotations

from prometheus_client import Counter

llmops_deployments_total = Counter(
    "llmops_deployments_total",
    "Count of deployment stage transitions (rollout success rate)",
    labelnames=("stage",),
)

llmops_rollbacks_total = Counter(
    "llmops_rollbacks_total",
    "Count of rollbacks (rollback frequency)",
    labelnames=("model_name",),
)

llmops_canary_gate_evaluations_total = Counter(
    "llmops_canary_gate_evaluations_total",
    "Count of canary gate evaluations",
    labelnames=("outcome",),
)
