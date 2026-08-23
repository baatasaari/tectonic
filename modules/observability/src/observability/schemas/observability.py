"""Request/response models for `/v1/observability/*` (LLD §3)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class SpanInput(BaseModel):
    span_id: str
    parent_span_id: str | None = None
    name: str
    service_name: str = "unknown"
    start_time: datetime
    end_time: datetime
    attributes: dict[str, Any] = {}
    status: str = "ok"


class IngestRequest(BaseModel):
    tenant_id: str
    trace_id: str
    workflow_type: str | None = None
    spans: list[SpanInput]


class IngestResponse(BaseModel):
    trace_id: str
    spans_ingested: int


class ReasoningNarrativeResponse(BaseModel):
    trace_id: str
    narrative: str
    span_count: int


class CostAttributionEntrySchema(BaseModel):
    span_id: str
    name: str
    duration_seconds: float
    input_tokens: int
    output_tokens: int
    cost_usd: float


class CostAttributionResponse(BaseModel):
    trace_id: str
    entries: list[CostAttributionEntrySchema]
    total_cost_usd: float


class TraceCompletenessResponse(BaseModel):
    tenant_id: str
    completeness_ratio: float
    traces_checked: int
    traces_with_known_shape: int
