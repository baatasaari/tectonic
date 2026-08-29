"""Prometheus metrics (LLD §Level 4 "Metrics")."""
from __future__ import annotations

from prometheus_client import Counter, Gauge

billing_invoices_generated_total = Counter(
    "billing_invoices_generated_total",
    "Count of invoice generations (metering accuracy's raw signal)",
    labelnames=("complete",),
)

billing_period_revenue_usd = Gauge(
    "billing_period_revenue_usd",
    "Total invoiced amount for the most recently generated invoice, per tenant",
    labelnames=("tenant_id",),
)

billing_metering_skipped_not_entitled_total = Counter(
    "billing_metering_skipped_not_entitled_total",
    "Count of resources skipped during metering because the tenant's real Multi-tenancy "
    "entitlement gate currently denies that module -- a deliberate exclusion, not missing data",
    labelnames=("resource",),
)
