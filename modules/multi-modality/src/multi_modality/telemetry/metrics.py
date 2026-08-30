"""Prometheus metrics (LLD §Level 4 "Metrics")."""
from __future__ import annotations

from prometheus_client import Counter, Histogram

multi_modality_extractions_total = Counter(
    "multi_modality_extractions_total",
    "Count of extractions performed",
    labelnames=("modality",),
)

multi_modality_extraction_latency_seconds = Histogram(
    "multi_modality_extraction_latency_seconds",
    "Extraction latency (conversion latency, the LLD's own key metric)",
    labelnames=("modality",),
)

multi_modality_groundedness_checks_total = Counter(
    "multi_modality_groundedness_checks_total",
    "Count of groundedness gate outcomes",
    labelnames=("decision",),
)
