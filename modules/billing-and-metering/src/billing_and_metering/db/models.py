"""SQLAlchemy 2.0 declarative models for the Billing and Metering data
model (LLD §3): PricingPlan, UsageRecord, Invoice, InvoiceLine.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CHAR, JSON, Boolean, DateTime, Float, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from billing_and_metering.db.base import Base


def _new_id() -> str:
    return str(uuid.uuid4())


UUIDType = UUID(as_uuid=False).with_variant(CHAR(36), "sqlite")


class PricingPlan(Base):
    __tablename__ = "pricing_plans"

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str | None] = mapped_column(String(255), nullable=True)  # None == global default plan
    name: Mapped[str] = mapped_column(String(255))
    unit_prices: Mapped[dict] = mapped_column(JSON(), default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UsageRecord(Base):
    __tablename__ = "usage_records"
    # The metering ledger's own idempotency key -- see BillingRepository.upsert_usage_record's
    # docstring (core/ports.py). Real Postgres ON CONFLICT target, not just documentation.
    __table_args__ = (UniqueConstraint("tenant_id", "period", "resource", name="uq_usage_records_tenant_period_resource"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    period: Mapped[str] = mapped_column(String(16))
    resource: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[float] = mapped_column(Float())
    source: Mapped[str] = mapped_column(String(32))
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Invoice(Base):
    __tablename__ = "invoices"
    # One invoice per (tenant, period), ever -- idempotent generation
    # (InvoiceService.generate_invoice) relies on this real constraint, not just
    # application-level check-then-act, to stay correct under a concurrent retry.
    __table_args__ = (UniqueConstraint("tenant_id", "period", name="uq_invoices_tenant_period"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    period: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="draft")
    total_amount: Mapped[float] = mapped_column(Float(), default=0.0)
    complete: Mapped[bool] = mapped_column(Boolean(), default=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    invoice_id: Mapped[str] = mapped_column(String(255))
    resource: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[float] = mapped_column(Float())
    unit_price: Mapped[float] = mapped_column(Float())
    amount: Mapped[float] = mapped_column(Float())
