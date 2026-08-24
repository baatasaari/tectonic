"""Prometheus metrics (LLD §Level 4 "Metrics")."""
from __future__ import annotations

from prometheus_client import Counter, Histogram

mcp_rpc_requests_total = Counter(
    "mcp_rpc_requests_total",
    "Count of proxied MCP JSON-RPC requests",
    labelnames=("server_id", "method", "outcome"),
)

mcp_rpc_latency_seconds = Histogram(
    "mcp_rpc_latency_seconds",
    "Latency of proxied MCP JSON-RPC requests",
    labelnames=("server_id",),
)

mcp_capability_sync_total = Counter(
    "mcp_capability_sync_total",
    "Count of capability sync runs",
    labelnames=("server_id", "outcome"),
)
