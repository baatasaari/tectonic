"""Prometheus metrics (LLD §Level 4 "Metrics")."""
from __future__ import annotations

from prometheus_client import Counter, Gauge

agent_marketplace_listings_total = Counter(
    "agent_marketplace_listings_total",
    "Count of listing status transitions (catalogue growth)",
    labelnames=("status",),
)

agent_marketplace_usage_events_total = Counter(
    "agent_marketplace_usage_events_total",
    "Count of recorded reuse events",
    labelnames=("listing_id",),
)

agent_marketplace_sync_total = Counter(
    "agent_marketplace_sync_total",
    "Count of catalogue sync runs against Agent Cards",
    labelnames=("outcome",),
)

# A Gauge, not a Counter: "how many listings are stuck in pending_review right now" is a
# current-state question the AgentMarketplacePendingReviewBacklogHigh alert needs a
# point-in-time count for, not a monotonically increasing transition count.
agent_marketplace_pending_review_backlog = Gauge(
    "agent_marketplace_pending_review_backlog",
    "Count of listings currently in pending_review for longer than the review SLA",
)
