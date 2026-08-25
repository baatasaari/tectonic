"""Framework-agnostic domain objects (LLD §3 data model)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

LLM_COST_RESOURCE = "llm.cost_usd"


def now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid.uuid4())


class InvoiceStatus(StrEnum):
    DRAFT = "draft"
    FINALIZED = "finalized"


# The invoice lifecycle state machine: any transition not a value here is illegal and
# raises InvalidTransitionError -- the same shape this platform's other state machines
# already established. Invoicing is one-way, the same shape Secrets and Credential
# Management (Module 32) used for its own revocation lifecycle: a finalized invoice
# being un-finalized is not a thing real billing systems do either.
_LEGAL_TRANSITIONS: dict[InvoiceStatus, set[InvoiceStatus]] = {
    InvoiceStatus.DRAFT: {InvoiceStatus.FINALIZED},
    InvoiceStatus.FINALIZED: set(),
}


def is_legal_transition(from_status: InvoiceStatus, to_status: InvoiceStatus) -> bool:
    return to_status in _LEGAL_TRANSITIONS.get(from_status, set())


class PricingPlanNotFoundError(Exception):
    def __init__(self, tenant_id: str | None) -> None:
        super().__init__(f"No pricing plan found for tenant: {tenant_id!r} (and no global default plan exists)")


class InvoiceNotFoundError(Exception):
    def __init__(self, invoice_id: str) -> None:
        super().__init__(f"Invoice not found: {invoice_id}")


class InvalidTransitionError(Exception):
    def __init__(self, from_status: InvoiceStatus, to_status: InvoiceStatus) -> None:
        super().__init__(f"Illegal transition: {from_status.value} -> {to_status.value}")
        self.from_status = from_status
        self.to_status = to_status


@dataclass
class PricingPlanRecord:
    id: str
    tenant_id: str | None  # None == the global default plan
    name: str
    unit_prices: dict[str, float] = field(default_factory=dict)
    created_at: datetime = field(default_factory=now)


@dataclass
class MeteredUsageRecord:
    id: str
    tenant_id: str
    period: str
    resource: str
    quantity: float
    source: str  # "finops" | "auditability"
    computed_at: datetime = field(default_factory=now)


@dataclass
class InvoiceLineRecord:
    id: str
    invoice_id: str
    resource: str
    quantity: float
    unit_price: float
    amount: float


@dataclass
class InvoiceRecord:
    id: str
    tenant_id: str
    period: str
    status: InvoiceStatus = InvoiceStatus.DRAFT
    total_amount: float = 0.0
    complete: bool = True
    generated_at: datetime = field(default_factory=now)
    finalized_at: datetime | None = None


@dataclass
class GeneratedInvoice:
    """What `InvoiceService.generate_invoice` returns: the persisted
    invoice plus the line items that make it up, so a caller never has
    to make a second round trip to see what it was actually billed
    for."""

    invoice: InvoiceRecord
    lines: list[InvoiceLineRecord]
