"""Request/response models for `/v1/multi-modality/*` (LLD §3)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ExtractRequest(BaseModel):
    modality: str
    raw_content: str
    grounding_context: str | None = None


class ExtractionSchema(BaseModel):
    id: str
    tenant_id: str
    modality: str
    raw_content: str
    extracted_content: str
    grounding_context: str | None
    groundedness_decision: str
    groundedness_violation_category: str | None
    latency_ms: float
    created_at: datetime


class ExtractionListResponse(BaseModel):
    items: list[ExtractionSchema]
    total: int
    limit: int
    offset: int
