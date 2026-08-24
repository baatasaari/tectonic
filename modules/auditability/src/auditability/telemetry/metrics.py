"""Prometheus metrics (LLD §Level 4 "Metrics")."""
from __future__ import annotations

from prometheus_client import Counter, Histogram

auditability_events_ingested_total = Counter(
    "auditability_events_ingested_total",
    "Count of audit events ingested",
    labelnames=("tenant_id", "source_module", "event_type"),
)

auditability_chain_verification_total = Counter(
    "auditability_chain_verification_total",
    "Count of chain verification runs by result",
    labelnames=("tenant_id", "result"),
)

auditability_audit_pack_generation_seconds = Histogram(
    "auditability_audit_pack_generation_seconds",
    "Duration of audit pack generation",
)

auditability_nl_query_translation_seconds = Histogram(
    "auditability_nl_query_translation_seconds",
    "Duration of natural-language query translation",
)

auditability_nl_query_translation_failures_total = Counter(
    "auditability_nl_query_translation_failures_total",
    "Count of NL query translation failures",
    labelnames=("reason",),
)
