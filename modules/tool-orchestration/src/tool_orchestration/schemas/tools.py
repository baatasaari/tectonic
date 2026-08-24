"""Request/response models for `/v1/tool-orchestration/*` (LLD §3.3)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ToolDefinitionSummary(BaseModel):
    id: str
    name: str
    mcp_server_ref: str
    status: str
    synthesised: bool


class ToolDefinitionListResponse(BaseModel):
    items: list[ToolDefinitionSummary]
    total: int
    limit: int
    offset: int


class ReliabilityScoreSummary(BaseModel):
    rolling_success_rate: float
    rolling_avg_latency_ms: float
    last_updated_at: datetime


class ToolDefinitionDetail(BaseModel):
    id: str
    tenant_id: str
    name: str
    mcp_server_ref: str
    schema_: dict[str, Any]
    status: str
    synthesised: bool
    created_at: datetime
    reliability_score: ReliabilityScoreSummary | None = None


class InvokeToolRequest(BaseModel):
    tool_id: str
    parameters: dict[str, Any] = {}
    agent_ref: str
    workflow_instance_id: str | None = None


class InvokeToolResponse(BaseModel):
    result: dict[str, Any] | None
    status: str
    retry_count: int
    latency_ms: float


class SynthesiseToolRequest(BaseModel):
    gap_description: str
    available_primitives: list[str] = []


class ApproveToolRequest(BaseModel):
    approved_by: str


class ApproveToolResponse(BaseModel):
    status: str
