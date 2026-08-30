"""Prometheus metrics (LLD §Level 4 "Metrics")."""
from __future__ import annotations

from prometheus_client import Counter

promptops_prompt_versions_total = Counter(
    "promptops_prompt_versions_total",
    "Count of prompt versions by status (version count, the LLD's own key metric)",
    labelnames=("status",),
)

promptops_ab_tests_concluded_total = Counter(
    "promptops_ab_tests_concluded_total",
    "Count of concluded A/B tests (A/B significance rate = significant / total concluded)",
    labelnames=("significant",),
)

promptops_drift_incidents_total = Counter(
    "promptops_drift_incidents_total",
    "Count of detected drift incidents (the LLD's own key metric)",
    labelnames=("prompt_name",),
)

promptops_reflection_runs_total = Counter(
    "promptops_reflection_runs_total",
    "Count of Reflection Optimiser runs",
    labelnames=("outcome",),
)
