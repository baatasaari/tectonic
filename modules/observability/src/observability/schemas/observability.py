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


class SpanSchema(BaseModel):
    id: str
    tenant_id: str
    trace_id: str
    span_id: str
    parent_span_id: str | None
    name: str
    service_name: str
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    attributes: dict[str, Any]
    status: str
    workflow_type: str | None


class TraceSummarySchema(BaseModel):
    trace_id: str
    tenant_id: str
    workflow_type: str | None
    span_count: int
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    has_error: bool


class TraceListResponse(BaseModel):
    items: list[TraceSummarySchema]
    total: int
    limit: int
    offset: int


class TraceDetailResponse(BaseModel):
    trace_id: str
    tenant_id: str
    spans: list[SpanSchema]


class CreateSLORequest(BaseModel):
    tenant_id: str
    name: str
    metric: str
    target: float
    window_hours: int
    service_name: str | None = None


class SLOSchema(BaseModel):
    id: str
    tenant_id: str
    name: str
    metric: str
    target: float
    window_hours: int
    service_name: str | None
    created_at: datetime


class SLOListResponse(BaseModel):
    items: list[SLOSchema]
    total: int
    limit: int
    offset: int


class SLOEvaluationSchema(BaseModel):
    slo_id: str
    tenant_id: str
    metric: str
    target: float
    sample_count: int
    current_value: float | None
    compliant: bool | None
    error_budget_remaining: float | None
    evaluated_at: datetime


class CreateAlertRuleRequest(BaseModel):
    tenant_id: str
    name: str
    metric: str
    comparison: str
    threshold: float
    window_hours: int
    service_name: str | None = None


class AlertRuleSchema(BaseModel):
    id: str
    tenant_id: str
    name: str
    metric: str
    comparison: str
    threshold: float
    window_hours: int
    service_name: str | None
    enabled: bool
    created_at: datetime


class AlertRuleListResponse(BaseModel):
    items: list[AlertRuleSchema]
    total: int
    limit: int
    offset: int


class AlertEventSchema(BaseModel):
    id: str
    rule_id: str
    tenant_id: str
    status: str
    value: float
    threshold: float
    triggered_at: datetime
    resolved_at: datetime | None


class AlertEventListResponse(BaseModel):
    items: list[AlertEventSchema]
    total: int
    limit: int
    offset: int
