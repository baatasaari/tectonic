"""In-memory fakes for unit tests (LLD "Deployability and testability
contract")."""
from __future__ import annotations

from typing import Any

from billing_and_metering.core.domain import (
    InvoiceLineRecord,
    InvoiceRecord,
    InvoiceStatus,
    MeteredUsageRecord,
    PricingPlanRecord,
)


class InMemoryBillingRepository:
    def __init__(self) -> None:
        self.pricing_plans: dict[str, PricingPlanRecord] = {}
        self.usage_records: list[MeteredUsageRecord] = []
        self.invoices: dict[str, InvoiceRecord] = {}
        self.invoice_lines: dict[str, list[InvoiceLineRecord]] = {}

    async def create_pricing_plan(self, record: PricingPlanRecord) -> PricingPlanRecord:
        self.pricing_plans[record.id] = record
        return record

    async def get_pricing_plan(self, plan_id: str) -> PricingPlanRecord | None:
        return self.pricing_plans.get(plan_id)

    async def get_pricing_plan_for_tenant(self, tenant_id: str) -> PricingPlanRecord | None:
        candidates = [p for p in self.pricing_plans.values() if p.tenant_id == tenant_id]
        return max(candidates, key=lambda p: p.created_at) if candidates else None

    async def get_default_pricing_plan(self) -> PricingPlanRecord | None:
        candidates = [p for p in self.pricing_plans.values() if p.tenant_id is None]
        return max(candidates, key=lambda p: p.created_at) if candidates else None

    async def list_pricing_plans(
        self, *, tenant_id: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[PricingPlanRecord], int]:
        results = list(self.pricing_plans.values())
        if tenant_id is not None:
            results = [p for p in results if p.tenant_id == tenant_id]
        results = sorted(results, key=lambda p: p.created_at)
        return results[offset:offset + limit], len(results)

    async def create_usage_record(self, record: MeteredUsageRecord) -> MeteredUsageRecord:
        self.usage_records.append(record)
        return record

    async def upsert_usage_record(self, record: MeteredUsageRecord) -> MeteredUsageRecord:
        for i, existing in enumerate(self.usage_records):
            if (existing.tenant_id, existing.period, existing.resource) == (record.tenant_id, record.period, record.resource):
                self.usage_records[i] = record
                return record
        self.usage_records.append(record)
        return record

    async def list_usage_records(
        self, *, tenant_id: str | None = None, period: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[MeteredUsageRecord], int]:
        results = list(self.usage_records)
        if tenant_id is not None:
            results = [r for r in results if r.tenant_id == tenant_id]
        if period is not None:
            results = [r for r in results if r.period == period]
        results = sorted(results, key=lambda r: r.computed_at, reverse=True)
        return results[offset:offset + limit], len(results)

    async def create_invoice(self, record: InvoiceRecord) -> InvoiceRecord:
        self.invoices[record.id] = record
        self.invoice_lines.setdefault(record.id, [])
        return record

    async def get_invoice(self, invoice_id: str) -> InvoiceRecord | None:
        return self.invoices.get(invoice_id)

    async def get_invoice_for_tenant_period(self, *, tenant_id: str, period: str) -> InvoiceRecord | None:
        for invoice in self.invoices.values():
            if invoice.tenant_id == tenant_id and invoice.period == period:
                return invoice
        return None

    async def update_invoice(self, record: InvoiceRecord) -> InvoiceRecord:
        self.invoices[record.id] = record
        return record

    async def list_invoices(
        self, *, tenant_id: str | None = None, status: InvoiceStatus | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[InvoiceRecord], int]:
        results = list(self.invoices.values())
        if tenant_id is not None:
            results = [i for i in results if i.tenant_id == tenant_id]
        if status is not None:
            results = [i for i in results if i.status == status]
        results = sorted(results, key=lambda i: i.generated_at, reverse=True)
        return results[offset:offset + limit], len(results)

    async def create_invoice_line(self, record: InvoiceLineRecord) -> InvoiceLineRecord:
        self.invoice_lines.setdefault(record.invoice_id, []).append(record)
        return record

    async def replace_invoice_lines(
        self, *, invoice_id: str, records: list[InvoiceLineRecord],
    ) -> list[InvoiceLineRecord]:
        self.invoice_lines[invoice_id] = list(records)
        return records

    async def list_invoice_lines(self, *, invoice_id: str) -> list[InvoiceLineRecord]:
        return list(self.invoice_lines.get(invoice_id, []))


class StubFinOpsClient:
    def __init__(self, *, total_cost: float = 0.0, raise_error: bool = False) -> None:
        self.total_cost = total_cost
        self.raise_error = raise_error
        self.calls: list[dict[str, Any]] = []

    async def get_total_cost(self, *, tenant_id: str, period: str) -> float:
        if self.raise_error:
            raise RuntimeError("finops is down")
        self.calls.append({"tenant_id": tenant_id, "period": period})
        return self.total_cost


class StubAuditabilityClient:
    def __init__(self, *, count: int = 0, raise_error: bool = False) -> None:
        self.count = count
        self.raise_error = raise_error
        self.calls: list[dict[str, Any]] = []

    async def count_events(
        self, *, tenant_id: str, source_module: str, occurred_after: Any = None, occurred_before: Any = None,
    ) -> int:
        if self.raise_error:
            raise RuntimeError("auditability is down")
        self.calls.append({"tenant_id": tenant_id, "source_module": source_module})
        return self.count


class StubMultiTenancyClient:
    """Records every sync/gate call and never raises -- mirrors
    `HTTPMultiTenancyClient`'s own best-effort/fail-open contracts, so a
    caller test never needs a try/except around either. `.allow`/
    `.reason` script every `gate()` call's verdict, same as Secrets and
    Credential Management's `StubIdentityAccessClient`."""

    def __init__(self, *, allow: bool = True, reason: str = "", denied_modules: set[str] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.gate_calls: list[dict[str, Any]] = []
        self.allow = allow
        self.reason = reason
        self.denied_modules = denied_modules or set()

    async def sync_entitlements(self, *, tenant_id: str, module_names: list[str]) -> None:
        self.calls.append({"tenant_id": tenant_id, "module_names": module_names})

    async def gate(self, *, tenant_id: str, module: str) -> tuple[bool, str]:
        self.gate_calls.append({"tenant_id": tenant_id, "module": module})
        if module in self.denied_modules:
            return False, self.reason or f"tenant not entitled to {module}"
        return self.allow, self.reason


__all__ = [
    "InMemoryBillingRepository", "StubAuditabilityClient", "StubFinOpsClient", "StubMultiTenancyClient",
]
