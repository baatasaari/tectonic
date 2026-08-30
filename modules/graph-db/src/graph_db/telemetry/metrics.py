"""Prometheus metrics (LLD §Level 4 "Metrics")."""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

graph_db_queries_total = Counter(
    "graph_db_queries_total",
    "Count of query requests",
    labelnames=("tenant_id", "query_type"),
)

graph_db_query_duration_seconds = Histogram(
    "graph_db_query_duration_seconds",
    "Duration of a query request",
    labelnames=("tenant_id", "traversal_depth_bucket"),
)

graph_db_writes_total = Counter(
    "graph_db_writes_total",
    "Count of node/edge writes",
    labelnames=("tenant_id", "element_type", "edge_kind"),
)

graph_db_node_count = Gauge(
    "graph_db_node_count",
    "Count of nodes",
    labelnames=("tenant_id",),
)

graph_db_edge_count = Gauge(
    "graph_db_edge_count",
    "Count of edges",
    labelnames=("tenant_id", "edge_kind"),
)
