"""Invoice Service (LLD §2 sub-components): aggregates metered usage
into invoice lines and a total, and owns the invoice's one-way
`draft -> finalized` lifecycle.
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

        invoice = await self._repository.create_invoice(InvoiceRecord(
            id=new_id(), tenant_id=tenant_id, period=period, total_amount=total_amount, complete=complete,
        ))

        lines = []
        for line in pending_lines:
            line.invoice_id = invoice.id
            lines.append(await self._repository.create_invoice_line(line))

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
