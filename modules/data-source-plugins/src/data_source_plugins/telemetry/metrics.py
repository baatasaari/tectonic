"""Prometheus metrics (LLD §Level 4 "Metrics")."""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

data_source_syncs_total = Counter(
    "data_source_syncs_total",
    "Count of sync attempts",
    labelnames=("tenant_id", "source_type", "outcome"),
)

data_source_sync_duration_seconds = Histogram(
    "data_source_sync_duration_seconds",
    "Duration of a sync run",
    labelnames=("source_type",),
)

data_source_freshness_lag_seconds = Gauge(
    "data_source_freshness_lag_seconds",
    "Time since last successful sync",
    labelnames=("connector_id",),
)

data_source_quality_score = Gauge(
    "data_source_quality_score",
    "Latest overall quality score",
    labelnames=("connector_id",),
)

data_source_drift_incidents_total = Counter(
    "data_source_drift_incidents_total",
    "Count of drift incidents",
    labelnames=("connector_id", "auto_adapted"),
)
