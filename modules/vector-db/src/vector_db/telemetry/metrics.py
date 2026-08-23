"""Prometheus metrics (LLD §Level 4 "Metrics")."""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

vector_db_queries_total = Counter(
    "vector_db_queries_total",
    "Count of query requests",
    labelnames=("tenant_id", "hybrid"),
)

vector_db_query_duration_seconds = Histogram(
    "vector_db_query_duration_seconds",
    "Duration of a query request",
    labelnames=("tenant_id",),
)

vector_db_points_total = Gauge(
    "vector_db_points_total",
    "Count of indexed points",
    labelnames=("tenant_id",),
)

vector_db_migration_progress_ratio = Gauge(
    "vector_db_migration_progress_ratio",
    "Progress ratio of an active migration",
    labelnames=("migration_id",),
)
