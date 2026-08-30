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

    async def upsert_usage_record(self, record: MeteredUsageRecord) -> MeteredUsageRecord:
        """The metering ledger's own idempotency: `(tenant_id, period,
        resource)` is a real unique key, so re-metering the same period
        (a retried scheduler run, a re-triggered `generate_invoice`)
        converges to one authoritative row per resource instead of
        accumulating duplicates that would double-count on the next
        invoice. A real atomic `INSERT ... ON CONFLICT DO UPDATE` at the
        SQL layer (`db/repository.py`) -- see Multi-tenancy's own
        `increment_quota_counter` for the same shape applied to a
        different table."""
        ...

    async def list_usage_records(
        self, *, tenant_id: str | None = None, period: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[MeteredUsageRecord], int]: ...

    async def create_invoice(self, record: InvoiceRecord) -> InvoiceRecord:
        """Real `(tenant_id, period)` uniqueness backs this too (see
        `MeteredUsageRecord`'s note above) -- a concurrent second caller
        racing to create the same period's invoice gets the first
        caller's own row back rather than a duplicate."""
        ...

    async def get_invoice(self, invoice_id: str) -> InvoiceRecord | None: ...

    async def get_invoice_for_tenant_period(self, *, tenant_id: str, period: str) -> InvoiceRecord | None:
        """The other half of idempotent invoice generation:
        `InvoiceService.generate_invoice` checks this first so a retried
        or re-triggered call for a period that already has an invoice
        updates that same row (if still `draft`) or returns it unchanged
        (if `finalized`) instead of creating a duplicate."""
        ...

    async def update_invoice(self, record: InvoiceRecord) -> InvoiceRecord: ...

    async def list_invoices(
        self, *, tenant_id: str | None = None, status: InvoiceStatus | None = None,
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[InvoiceRecord], int]: ...

    async def create_invoice_line(self, record: InvoiceLineRecord) -> InvoiceLineRecord: ...

    async def replace_invoice_lines(
        self, *, invoice_id: str, records: list[InvoiceLineRecord],
    ) -> list[InvoiceLineRecord]:
        """Wholesale-replaces a draft invoice's line items -- never a
        field-by-field patch, the same "a plan change fully re-derives
        the set" posture Multi-tenancy's entitlements/quota-set replace
        endpoints already take. Re-metering a period whose resource set
        changed (a pricing plan edit, a resource that's no longer
        entitled) must never leave a stale line behind."""
        ...

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


class MultiTenancyClient(Protocol):
    async def sync_entitlements(self, *, tenant_id: str, module_names: list[str]) -> None:
        """Pushes this tenant's current module list to Multi-tenancy's
        feature-flag store. Best-effort: implementations must swallow
        their own failures (log and return) rather than raise -- a
        pricing plan is a committed billing record the moment it's
        created, and Multi-tenancy being unreachable must never block or
        fail that."""
        ...

    async def gate(self, *, tenant_id: str, module: str) -> tuple[bool, str]:
        """Calls Multi-tenancy's real `GET /tenants/{id}/gate?module=X` --
        the same real entitlement check `EntitlementGateMiddleware` uses
        platform-wide, reused here so `MeteringService` never meters (and
        therefore never bills) a resource for a module the tenant isn't
        currently entitled to. Implementations must fail OPEN
        (`(True, "")`, with a logged warning) if Multi-tenancy is
        unreachable -- the same deliberate contrast with zero-trust auth
        every other use of this endpoint in this platform already takes:
        a commercial gate must never turn a billing outage into missed
        revenue on top of the outage itself."""
        ...
