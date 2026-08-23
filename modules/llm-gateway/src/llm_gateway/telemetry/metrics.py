"""Prometheus metrics (LLD §Level 4 "Metrics")."""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

llm_gateway_requests_total = Counter(
    "llm_gateway_requests_total",
    "Count of gateway requests",
    labelnames=("tenant_id", "provider", "model", "outcome"),
)

llm_gateway_request_duration_seconds = Histogram(
    "llm_gateway_request_duration_seconds",
    "Full request duration including provider inference time",
    labelnames=("provider", "model"),
)

llm_gateway_overhead_seconds = Histogram(
    "llm_gateway_overhead_seconds",
    "Gateway-added latency only, excludes provider inference time",
    buckets=(0.001, 0.0025, 0.005, 0.01, 0.015, 0.025, 0.05, 0.1),
)

llm_gateway_cache_hit_ratio = Gauge(
    "llm_gateway_cache_hit_ratio",
    "Rolling cache hit ratio",
    labelnames=("tenant_id",),
)

llm_gateway_cost_total = Counter(
    "llm_gateway_cost_total",
    "Cumulative spend",
    labelnames=("tenant_id", "provider", "model"),
)

llm_gateway_failover_total = Counter(
    "llm_gateway_failover_total",
    "Count of failovers from one provider to another",
    labelnames=("from_provider", "to_provider"),
)

llm_gateway_budget_utilisation_ratio = Gauge(
    "llm_gateway_budget_utilisation_ratio",
    "current_spend / limit_amount",
    labelnames=("tenant_id", "budget_policy_id"),
)

llm_gateway_deprecation_notices_total = Counter(
    "llm_gateway_deprecation_notices_total",
    "Count of newly detected provider model deprecation notices",
    labelnames=("provider",),
)
