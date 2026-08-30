"""Request/response models for `/v1/billing/*` (LLD §3)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator

Period = Literal["daily", "monthly"]


def _reject_null_byte(value: str) -> str:
    """Postgres's `text`/`json` columns are UTF-8 and reject the NUL byte
    outright (`asyncpg.exceptions.CharacterNotInRepertoireError`) -- a
    value `str` is happy to hold but the database is not. Schema-valid per
    OpenAPI (`type: string` says nothing about NUL), so nothing upstream of
    the DB call rejects it without this: caught here as a clean `422`
    instead of the request reaching the database at all."""
    if "\x00" in value:
        raise ValueError("must not contain a NUL byte (unsupported by Postgres's text encoding)")
    return value


class CreatePricingPlanRequest(BaseModel):
    tenant_id: str | None = None
    name: str
    unit_prices: dict[str, float]

    @field_validator("tenant_id", "name")
    @classmethod
    def _validate_no_null_byte(cls, value: str | None) -> str | None:
        return _reject_null_byte(value) if value is not None else value

    @field_validator("unit_prices")
    @classmethod
    def _validate_unit_price_keys(cls, value: dict[str, float]) -> dict[str, float]:
        for key in value:
            _reject_null_byte(key)
        return value


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

    @field_validator("tenant_id")
    @classmethod
    def _validate_no_null_byte(cls, value: str) -> str:
        return _reject_null_byte(value)


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


class MeterTenantResponse(BaseModel):
    """Ticket #82 (Phase 2 support-agent slice): before this, MeteringService
    .meter_tenant() -- real, tested, idempotent code -- had no real HTTP
    trigger at all, the same "who calls this periodically" gap this
    platform already documents for other modules' own background
    computations (e.g. Multi-tenancy's isolation probe, Observability's own
    SLO/alert evaluate endpoints), except those at least exposed the
    computation as a callable endpoint -- this module never had."""

    tenant_id: str
    period: str
    records: list[UsageRecordSchema]
    complete: bool
