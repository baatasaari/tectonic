"""Request/response models for `/v1/a2a/*` (LLD §3)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class DelegateRequest(BaseModel):
    target_agent_url: str
    skill_id: str
    input_message: dict[str, Any] = {}


class TaskSchema(BaseModel):
    id: str
    tenant_id: str
    direction: str
    peer_agent_url: str
    skill_id: str
    status: str
    input_message: dict[str, Any]
    output_artifacts: list[dict[str, Any]]
    error: str | None
    created_at: datetime
    updated_at: datetime


class TaskListResponse(BaseModel):
    items: list[TaskSchema]
    total: int
    limit: int
    offset: int


class SetAccessPolicyRequest(BaseModel):
    allowed_skills: list[str] | None = None


class AccessPolicySchema(BaseModel):
    caller_agent_id: str
    tenant_id: str
    allowed_skills: list[str] | None


class AgentSkillSchema(BaseModel):
    id: str
    name: str
    description: str = ""


class AgentCardSchema(BaseModel):
    name: str
    description: str
    url: str
    skills: list[AgentSkillSchema] = []


class JsonRpcRequestSchema(BaseModel):
    jsonrpc: str = "2.0"
    method: str
    params: dict[str, Any] | None = None
    id: str | int | None = None


class JsonRpcResponseSchema(BaseModel):
    jsonrpc: str = "2.0"
    id: str | int | None = None
    result: Any | None = None
    error: dict[str, Any] | None = None
