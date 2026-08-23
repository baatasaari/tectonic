"""Prometheus metrics (LLD §Level 4 "Metrics")."""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

intent_classifications_total = Counter(
    "intent_classifications_total",
    "Count of classification requests",
    labelnames=("tenant_id", "fallback_used"),
)

intent_classification_duration_seconds = Histogram(
    "intent_classification_duration_seconds",
    "Duration of a classification request",
    labelnames=("tenant_id", "fallback_used"),
)

intent_confidence_score = Histogram(
    "intent_confidence_score",
    "Confidence score of the top detected intent",
    labelnames=("tenant_id",),
)

intent_drift_score = Gauge(
    "intent_drift_score",
    "Latest computed drift score",
    labelnames=("tenant_id", "taxonomy_version"),
)
