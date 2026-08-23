"""Request/response models for the `/v1/workflow-engine/instances` endpoints
(LLD §3.3)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class StartInstanceRequest(BaseModel):
    definition_id: str
    definition_version: int | None = None
    initial_context: dict[str, Any] = {}


class StartInstanceResponse(BaseModel):
    id: str
    status: str
    trace_id: str


class StepExecutionSummary(BaseModel):
    id: str
    step_id: str
    execution_mode: str
    status: str
    confidence_score: float | None = None
    retry_count: int
    started_at: datetime | None = None
    completed_at: datetime | None = None


class InstanceDetail(BaseModel):
    id: str
    definition_id: str
    definition_version: int
    status: str
    current_step_ids: list[str]
    context: dict[str, Any]
    tenant_id: str
    trace_id: str
    started_at: datetime
    completed_at: datetime | None = None
    steps: list[StepExecutionSummary] = []


class PauseRequest(BaseModel):
    reason: str


class TerminateRequest(BaseModel):
    reason: str


class StatusResponse(BaseModel):
    status: str


class ApprovalCallbackRequest(BaseModel):
    decision: str  # "approved" | "rejected"
    resolved_by: str
