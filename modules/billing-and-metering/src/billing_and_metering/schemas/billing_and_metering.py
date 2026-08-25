"""Request/response models for `/v1/billing/*` (LLD §3)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

Period = Literal["daily", "monthly"]


class CreatePricingPlanRequest(BaseModel):
    tenant_id: str | None = None
    name: str
    unit_prices: dict[str, float]


class PricingPlanSchema(BaseModel):
    id: str
    tenant_id: str | None
    name: str
    unit_prices: dict[str, float]
    created_at: datetime


class PricingPlanListResponse(BaseModel):
    items: list[PricingPlanSchema]
    total: int
    limit: int
    offset: int


class GenerateInvoiceRequest(BaseModel):
    tenant_id: str
    period: Period


class InvoiceLineSchema(BaseModel):
    id: str
    invoice_id: str
    resource: str
    quantity: float
    unit_price: float
    amount: float


class InvoiceSchema(BaseModel):
    id: str
    tenant_id: str
    period: str
    status: str
    total_amount: float
    complete: bool
    generated_at: datetime
    finalized_at: datetime | None


class GeneratedInvoiceSchema(BaseModel):
    invoice: InvoiceSchema
    lines: list[InvoiceLineSchema]


class InvoiceListResponse(BaseModel):
    items: list[InvoiceSchema]
    total: int
    limit: int
    offset: int


class UsageRecordSchema(BaseModel):
    id: str
    tenant_id: str
    period: str
    resource: str
    quantity: float
    source: str
    computed_at: datetime


class UsageRecordListResponse(BaseModel):
    items: list[UsageRecordSchema]
    total: int
    limit: int
    offset: int
