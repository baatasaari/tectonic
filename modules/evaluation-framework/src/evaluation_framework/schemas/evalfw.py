"""Request/response models for `/v1/evaluation-framework/*` (LLD §3)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class MetricScoreSchema(BaseModel):
    id: str
    metric_name: str
    score: float
    threshold: float
    passed: bool
    created_at: datetime


class MetricScoreListResponse(BaseModel):
    items: list[MetricScoreSchema]
    total: int
    limit: int
    offset: int


class EvaluateRequest(BaseModel):
    tenant_id: str
    agent_ref: str
    agent_output: str
    reference_data: dict[str, Any] | None = None
    metric_set: list[str]
    trigger_source: str = "ci_cd"


class EvalRunSchema(BaseModel):
    id: str
    tenant_id: str
    trigger_source: str
    agent_ref: str
    metrics_evaluated: list[str]
    status: str
    started_at: datetime
    completed_at: datetime | None
    scores: list[MetricScoreSchema] = []


class GateRequest(BaseModel):
    tenant_id: str
    eval_run_id: str
    environment: str = "production"


class GateResultSchema(BaseModel):
    id: str
    eval_run_id: str
    overall_passed: bool
    blocking_failures: list[str]
    environment: str
    created_at: datetime


class CreateDomainPackRequest(BaseModel):
    tenant_id: str
    pack_name: str
    custom_thresholds: dict[str, float] = {}


class DomainMetricPackSchema(BaseModel):
    id: str
    tenant_id: str
    pack_name: str
    enabled: bool
    custom_thresholds: dict[str, float]


class SampleRequest(BaseModel):
    tenant_id: str
    interaction_id: str
    agent_ref: str
    agent_output: str
    reference_data: dict[str, Any] | None = None
    metric_set: list[str]


class SampleResponse(BaseModel):
    sampled: bool
    eval_run_id: str | None = None
