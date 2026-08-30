"""Request/response models for `/v1/auditability/*` (LLD §3)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AuditEventSchema(BaseModel):
    id: str
    tenant_id: str
    source_module: str
    event_type: str
    payload: dict[str, Any]
    sequence_number: int
    entry_hash: str
    prev_hash: str | None
    occurred_at: datetime


class AuditEventListResponse(BaseModel):
    items: list[AuditEventSchema]
    total: int
    limit: int
    offset: int


class ChainVerificationResponse(BaseModel):
    tenant_id: str
    valid: bool
    verified_count: int
    break_at_sequence: int | None = None


class CreateAuditPackRequest(BaseModel):
    tenant_id: str
    event_type: str | None = None
    source_module: str | None = None
    control_name: str | None = None
    occurred_after: datetime | None = None
    occurred_before: datetime | None = None


class AuditPackSchema(BaseModel):
    id: str
    tenant_id: str
    status: str
    event_count: int
    chain_valid: bool | None
    generated_at: datetime | None
    document_ref: str | None
    document_format: str
    document_bytes_b64: str | None = None
    created_at: datetime
    attempts: int
    last_error: str | None = None


class NLQueryRequest(BaseModel):
    question: str
    tenant_id: str


class NLQueryFilterEcho(BaseModel):
    """Echoes exactly what the translator derived, so a reviewer can see
    what was searched rather than just trusting the answer (LLD
    differentiator: "always echoes the structured filter it derived")."""

    event_type: str | None = None
    source_module: str | None = None
    control_name: str | None = None
    occurred_after: datetime | None = None
    occurred_before: datetime | None = None


class NLQueryResponse(BaseModel):
    filter_used: NLQueryFilterEcho
    results: AuditEventListResponse
