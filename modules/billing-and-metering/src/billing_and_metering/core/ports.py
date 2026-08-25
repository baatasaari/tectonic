"""Abstract ports this module depends on: persistence, and the two real
platform-peer clients the Metering Service pulls real usage from.
"""
from __future__ import annotations

from typing import Any, Protocol

from billing_and_metering.core.domain import (
    InvoiceLineRecord,
    InvoiceRecord,
    InvoiceStatus,
    MeteredUsageRecord,
    PricingPlanRecord,
)


class BillingRepository(Protocol):
    async def create_pricing_plan(self, record: PricingPlanRecord) -> PricingPlanRecord: ...

    async def get_pricing_plan(self, plan_id: str) -> PricingPlanRecord | None: ...

    async def get_pricing_plan_for_tenant(self, tenant_id: str) -> PricingPlanRecord | None:
        """The tenant-specific plan, if one exists -- `None` if the
        tenant has no plan of its own (the caller falls back to the
        global default)."""
        ...

    async def get_default_pricing_plan(self) -> PricingPlanRecord | None:
        """The one plan with `tenant_id is None`, if it exists."""
        ...

    async def list_pricing_plans(
        self, *, tenant_id: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[PricingPlanRecord], int]: ...

    async def create_usage_record(self, record: MeteredUsageRecord) -> MeteredUsageRecord: ...

    async def list_usage_records(
        self, *, tenant_id: str | None = None, period: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[MeteredUsageRecord], int]: ...

    async def create_invoice(self, record: InvoiceRecord) -> InvoiceRecord: ...

    async def get_invoice(self, invoice_id: str) -> InvoiceRecord | None: ...

    async def update_invoice(self, record: InvoiceRecord) -> InvoiceRecord: ...

    async def list_invoices(
        self, *, tenant_id: str | None = None, status: InvoiceStatus | None = None,
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[InvoiceRecord], int]: ...

    async def create_invoice_line(self, record: InvoiceLineRecord) -> InvoiceLineRecord: ...

    async def list_invoice_lines(self, *, invoice_id: str) -> list[InvoiceLineRecord]: ...


class FinOpsClient(Protocol):
    async def get_total_cost(self, *, tenant_id: str, period: str) -> float:
        """Calls FinOps's real `GET /v1/finops/cost-reports/{tenant_id}`
        and returns `total_cost`."""
        ...


class AuditabilityClient(Protocol):
    async def count_events(
        self, *, tenant_id: str, source_module: str, occurred_after: Any = None, occurred_before: Any = None,
    ) -> int:
        """Calls Auditability's real `GET /v1/auditability/events` and
        returns the `total` it reports -- never pages through and
        counts events itself."""
        ...
