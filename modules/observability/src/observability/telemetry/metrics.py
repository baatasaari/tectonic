"""Prometheus meta-metrics about the observability pipeline itself (LLD
§Level 4 "Metrics" — "this module is itself the telemetry destination")."""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

observability_ingestion_rate = Counter(
    "observability_ingestion_rate",
    "Count of spans ingested",
    labelnames=("source_module",),
)

observability_ingestion_latency_seconds = Histogram(
    "observability_ingestion_latency_seconds",
    "Time from span emission to queryable",
)

observability_trace_completeness_ratio = Gauge(
    "observability_trace_completeness_ratio",
    "Completeness ratio (spans present vs expected per known workflow shapes)",
    labelnames=("tenant_id",),
)

observability_reasoning_narrative_requests_total = Counter(
    "observability_reasoning_narrative_requests_total",
    "Count of reasoning-narrative requests",
    labelnames=("tenant_id",),
)

observability_storage_cost_per_million_spans = Gauge(
    "observability_storage_cost_per_million_spans",
    "Informational, feeds FinOps",
)
