"""Request/response models for `/v1/tool-orchestration/*` (LLD §3.3)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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


class RegisterToolRequest(BaseModel):
    """Ticket #82 (Phase 2 support-agent slice): before this, the only way
    through this module's own real API to create any ToolDefinition at all
    was `/synthesise` -- which always calls LLM Gateway to *invent* a
    proposal and always requires a Sentinel Agents review, appropriate for
    a genuinely novel LLM-synthesised tool but not for onboarding a known,
    already-specified integration an admin already vouches for (this
    slice's own get_order_status tool, e.g.) -- there was no way to do that
    without either standing up Sentinel Agents (out of this slice's scope
    entirely) or mischaracterising a known integration as `synthesised`.
    This endpoint registers a tool directly as `active`, `synthesised=False`,
    skipping the guarded synthesis/review pipeline -- that gate exists to
    guard LLM-invented tools, not admin-registered ones."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    mcp_server_ref: str
    schema_: dict[str, Any] = Field(default_factory=dict, alias="schema")


class RegisterToolResponse(BaseModel):
    id: str
    name: str
    mcp_server_ref: str
    status: str
    synthesised: bool


class SynthesiseToolRequest(BaseModel):
    gap_description: str
    available_primitives: list[str] = []


class ApproveToolRequest(BaseModel):
    approved_by: str


class ApproveToolResponse(BaseModel):
    status: str
