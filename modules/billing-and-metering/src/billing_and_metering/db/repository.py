"""SQLAlchemy-backed implementation of BillingRepository (LLD §3)."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from billing_and_metering.core.domain import (
    InvoiceLineRecord,
    InvoiceRecord,
    InvoiceStatus,
    MeteredUsageRecord,
    PricingPlanRecord,
)
from billing_and_metering.db import models


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _plan_to_domain(m: models.PricingPlan) -> PricingPlanRecord:
    return PricingPlanRecord(
        id=str(m.id), tenant_id=m.tenant_id, name=m.name, unit_prices=dict(m.unit_prices or {}),
        created_at=_as_utc(m.created_at),
    )


def _usage_to_domain(m: models.UsageRecord) -> MeteredUsageRecord:
    return MeteredUsageRecord(
        id=str(m.id), tenant_id=m.tenant_id, period=m.period, resource=m.resource, quantity=m.quantity,
        source=m.source, computed_at=_as_utc(m.computed_at),
    )


def _invoice_to_domain(m: models.Invoice) -> InvoiceRecord:
    return InvoiceRecord(
        id=str(m.id), tenant_id=m.tenant_id, period=m.period, status=InvoiceStatus(m.status),
        total_amount=m.total_amount, complete=m.complete, generated_at=_as_utc(m.generated_at),
        finalized_at=_as_utc(m.finalized_at),
    )


def _line_to_domain(m: models.InvoiceLine) -> InvoiceLineRecord:
    return InvoiceLineRecord(
        id=str(m.id), invoice_id=m.invoice_id, resource=m.resource, quantity=m.quantity,
        unit_price=m.unit_price, amount=m.amount,
    )


class SQLAlchemyBillingRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_pricing_plan(self, record: PricingPlanRecord) -> PricingPlanRecord:
        m = models.PricingPlan(
            id=record.id, tenant_id=record.tenant_id, name=record.name, unit_prices=record.unit_prices,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _plan_to_domain(m)

    async def get_pricing_plan(self, plan_id: str) -> PricingPlanRecord | None:
        m = await self.session.get(models.PricingPlan, plan_id)
        return _plan_to_domain(m) if m else None

    async def get_pricing_plan_for_tenant(self, tenant_id: str) -> PricingPlanRecord | None:
        stmt = (
            select(models.PricingPlan).where(models.PricingPlan.tenant_id == tenant_id)
            .order_by(models.PricingPlan.created_at.desc()).limit(1)
        )
        m = (await self.session.execute(stmt)).scalar_one_or_none()
        return _plan_to_domain(m) if m else None

    async def get_default_pricing_plan(self) -> PricingPlanRecord | None:
        stmt = (
            select(models.PricingPlan).where(models.PricingPlan.tenant_id.is_(None))
            .order_by(models.PricingPlan.created_at.desc()).limit(1)
        )
        m = (await self.session.execute(stmt)).scalar_one_or_none()
        return _plan_to_domain(m) if m else None

    async def list_pricing_plans(
        self, *, tenant_id: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[PricingPlanRecord], int]:
        filters = []
        if tenant_id is not None:
            filters.append(models.PricingPlan.tenant_id == tenant_id)

        count_stmt = select(func.count(models.PricingPlan.id)).where(*filters)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            select(models.PricingPlan).where(*filters).order_by(models.PricingPlan.created_at.desc())
            .limit(limit).offset(offset)
        )
        rows = await self.session.execute(stmt)
        return [_plan_to_domain(m) for m in rows.scalars().all()], total

    async def create_usage_record(self, record: MeteredUsageRecord) -> MeteredUsageRecord:
        m = models.UsageRecord(
            id=record.id, tenant_id=record.tenant_id, period=record.period, resource=record.resource,
            quantity=record.quantity, source=record.source,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _usage_to_domain(m)

    async def list_usage_records(
        self, *, tenant_id: str | None = None, period: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[MeteredUsageRecord], int]:
        filters = []
        if tenant_id is not None:
            filters.append(models.UsageRecord.tenant_id == tenant_id)
        if period is not None:
            filters.append(models.UsageRecord.period == period)

        count_stmt = select(func.count(models.UsageRecord.id)).where(*filters)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            select(models.UsageRecord).where(*filters).order_by(models.UsageRecord.computed_at.desc())
            .limit(limit).offset(offset)
        )
        rows = await self.session.execute(stmt)
        return [_usage_to_domain(m) for m in rows.scalars().all()], total

    async def create_invoice(self, record: InvoiceRecord) -> InvoiceRecord:
        m = models.Invoice(
            id=record.id, tenant_id=record.tenant_id, period=record.period, status=record.status.value,
            total_amount=record.total_amount, complete=record.complete, finalized_at=record.finalized_at,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _invoice_to_domain(m)

    async def get_invoice(self, invoice_id: str) -> InvoiceRecord | None:
        m = await self.session.get(models.Invoice, invoice_id)
        return _invoice_to_domain(m) if m else None

    async def update_invoice(self, record: InvoiceRecord) -> InvoiceRecord:
        m = await self.session.get(models.Invoice, record.id)
        m.status = record.status.value
        m.total_amount = record.total_amount
        m.complete = record.complete
        m.finalized_at = record.finalized_at
        await self.session.commit()
        await self.session.refresh(m)
        return _invoice_to_domain(m)

    async def list_invoices(
        self, *, tenant_id: str | None = None, status: InvoiceStatus | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[InvoiceRecord], int]:
        filters = []
        if tenant_id is not None:
            filters.append(models.Invoice.tenant_id == tenant_id)
        if status is not None:
            filters.append(models.Invoice.status == status.value)

        count_stmt = select(func.count(models.Invoice.id)).where(*filters)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            select(models.Invoice).where(*filters).order_by(models.Invoice.generated_at.desc())
            .limit(limit).offset(offset)
        )
        rows = await self.session.execute(stmt)
        return [_invoice_to_domain(m) for m in rows.scalars().all()], total

    async def create_invoice_line(self, record: InvoiceLineRecord) -> InvoiceLineRecord:
        m = models.InvoiceLine(
            id=record.id, invoice_id=record.invoice_id, resource=record.resource, quantity=record.quantity,
            unit_price=record.unit_price, amount=record.amount,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _line_to_domain(m)

    async def list_invoice_lines(self, *, invoice_id: str) -> list[InvoiceLineRecord]:
        stmt = select(models.InvoiceLine).where(models.InvoiceLine.invoice_id == invoice_id)
        rows = await self.session.execute(stmt)
        return [_line_to_domain(m) for m in rows.scalars().all()]
