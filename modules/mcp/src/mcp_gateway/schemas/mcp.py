"""Request/response models for `/v1/mcp/*` (LLD §3)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class RegisterServerRequest(BaseModel):
    name: str
    description: str = ""
    base_url: str


class McpToolSchema(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]


class McpServerSchema(BaseModel):
    id: str
    tenant_id: str
    name: str
    description: str
    base_url: str
    status: str
    created_at: datetime
    tools: list[McpToolSchema] = []


class McpServerListResponse(BaseModel):
    items: list[McpServerSchema]
    total: int
    limit: int
    offset: int


class SetAccessPolicyRequest(BaseModel):
    allowed_tools: list[str] | None = None


class AccessPolicySchema(BaseModel):
    server_id: str
    tenant_id: str
    allowed_tools: list[str] | None


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
