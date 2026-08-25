"""Prometheus metrics (LLD §Level 4 "Metrics")."""
from __future__ import annotations

from prometheus_client import Counter

finops_cost_reports_total = Counter(
    "finops_cost_reports_total",
    "Count of cost reports generated",
    labelnames=("tenant_id",),
)

finops_optimisation_actions_total = Counter(
    "finops_optimisation_actions_total",
    "Count of autonomous cost-optimisation actions taken",
    labelnames=("tenant_id", "action_type"),
)

finops_budget_alerts_total = Counter(
    "finops_budget_alerts_total",
    "Count of budget alert threshold breaches (budget adherence)",
    labelnames=("tenant_id",),
)
