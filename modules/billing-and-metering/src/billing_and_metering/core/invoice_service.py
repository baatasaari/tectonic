"""Invoice Service (LLD §2 sub-components): aggregates metered usage
into invoice lines and a total, and owns the invoice's one-way
`draft -> finalized` lifecycle.

`generate_invoice` is idempotent, the invoice-level half of this
module's idempotent metering ledger (see `core/metering_service.py`'s
own docstring for the usage-record half): calling it twice for the
same `(tenant_id, period)` never creates a second invoice. A `draft`
invoice for that period is re-metered and its lines wholesale-replaced
in place (a pricing plan edit or a newly-revoked entitlement must never
leave a stale line behind); a `finalized` one is returned completely
unchanged, without even re-metering -- invoicing is one-way, and a
finalized invoice is the truth for that period from then on, whatever
new usage arrives afterward.
"""
from __future__ import annotations

from billing_and_metering.core.domain import (
    GeneratedInvoice,
    InvalidTransitionError,
    InvoiceLineRecord,
    InvoiceNotFoundError,
    InvoiceRecord,
    InvoiceStatus,
    is_legal_transition,
    new_id,
    now,
)
from billing_and_metering.core.metering_service import MeteringService
from billing_and_metering.core.ports import BillingRepository
from billing_and_metering.core.pricing_plan_service import PricingPlanService
from billing_and_metering.telemetry.metrics import (
    billing_invoices_generated_total,
    billing_period_revenue_usd,
)


class InvoiceService:
    def __init__(
        self, repository: BillingRepository, pricing_plan_service: PricingPlanService, metering_service: MeteringService,
    ) -> None:
        self._repository = repository
        self._pricing_plan_service = pricing_plan_service
        self._metering_service = metering_service

    async def generate_invoice(self, *, tenant_id: str, period: str) -> GeneratedInvoice:
        existing = await self._repository.get_invoice_for_tenant_period(tenant_id=tenant_id, period=period)
        if existing is not None and existing.status == InvoiceStatus.FINALIZED:
            # Invoicing is one-way -- never re-meter, let alone re-total, a period
            # that's already been finalized, no matter what new usage has arrived since.
            lines = await self._repository.list_invoice_lines(invoice_id=existing.id)
            return GeneratedInvoice(invoice=existing, lines=lines)

        plan = await self._pricing_plan_service.resolve_active_plan(tenant_id)
        usage_records, complete = await self._metering_service.meter_tenant(
            tenant_id=tenant_id, period=period, plan=plan,
        )

        total_amount = 0.0
        pending_lines: list[InvoiceLineRecord] = []
        for record in usage_records:
            unit_price = plan.unit_prices.get(record.resource, 0.0)
            amount = record.quantity * unit_price
            total_amount += amount
            pending_lines.append(InvoiceLineRecord(
                id=new_id(), invoice_id="", resource=record.resource, quantity=record.quantity,
                unit_price=unit_price, amount=amount,
            ))

        if existing is not None:
            # A draft invoice for this period already exists (a retried call, a
            # re-triggered generation after usage changed) -- update it and
            # wholesale-replace its lines rather than creating a second invoice.
            existing.total_amount = total_amount
            existing.complete = complete
            existing.generated_at = now()
            invoice = await self._repository.update_invoice(existing)
        else:
            invoice = await self._repository.create_invoice(InvoiceRecord(
                id=new_id(), tenant_id=tenant_id, period=period, total_amount=total_amount, complete=complete,
            ))

        for line in pending_lines:
            line.invoice_id = invoice.id
        lines = await self._repository.replace_invoice_lines(invoice_id=invoice.id, records=pending_lines)

        billing_invoices_generated_total.labels(complete=str(complete)).inc()
        billing_period_revenue_usd.labels(tenant_id=tenant_id).set(total_amount)

        return GeneratedInvoice(invoice=invoice, lines=lines)

    async def get_invoice(self, invoice_id: str) -> GeneratedInvoice:
        invoice = await self._repository.get_invoice(invoice_id)
        if invoice is None:
            raise InvoiceNotFoundError(invoice_id)
        lines = await self._repository.list_invoice_lines(invoice_id=invoice_id)
        return GeneratedInvoice(invoice=invoice, lines=lines)

    async def list_invoices(
        self, *, tenant_id: str | None = None, status: InvoiceStatus | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[InvoiceRecord], int]:
        return await self._repository.list_invoices(tenant_id=tenant_id, status=status, limit=limit, offset=offset)

    async def finalize(self, invoice_id: str) -> InvoiceRecord:
        invoice = await self._repository.get_invoice(invoice_id)
        if invoice is None:
            raise InvoiceNotFoundError(invoice_id)
        if not is_legal_transition(invoice.status, InvoiceStatus.FINALIZED):
            raise InvalidTransitionError(invoice.status, InvoiceStatus.FINALIZED)
        invoice.status = InvoiceStatus.FINALIZED
        invoice.finalized_at = now()
        return await self._repository.update_invoice(invoice)
