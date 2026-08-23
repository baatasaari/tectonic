"""Prometheus metrics (LLD §Level 4 "Metrics")."""
from __future__ import annotations

from prometheus_client import Counter, Histogram

rag_retrievals_total = Counter(
    "rag_retrievals_total",
    "Count of retrieval requests",
    labelnames=("tenant_id", "outcome"),  # outcome: sufficient|max_hops_reached
)

rag_hop_count = Histogram(
    "rag_hop_count",
    "Number of hops per retrieval request",
    labelnames=("tenant_id",),
    buckets=(1, 2, 3, 4, 5),
)

rag_groundedness_score = Histogram(
    "rag_groundedness_score",
    "Final groundedness score per retrieval request",
    labelnames=("tenant_id",),
)

rag_retrieval_duration_seconds = Histogram(
    "rag_retrieval_duration_seconds",
    "Duration of one retrieval hop",
    labelnames=("tenant_id", "hop_number"),
)
