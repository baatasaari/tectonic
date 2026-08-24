"""Framework-agnostic domain objects (LLD §3 data model)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


def now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid.uuid4())


class ServerStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class McpServerNotFoundError(Exception):
    def __init__(self, server_id: str) -> None:
        super().__init__(f"MCP server not found: {server_id}")


class AccessDeniedError(Exception):
    """Raised by the Access Policy Engine — deny-by-default: no policy row
    for (server_id, tenant_id) means zero access, and a tools/call naming
    a tool outside the policy's allow-list is denied the same way."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class McpServerRecord:
    id: str
    tenant_id: str
    name: str
    description: str
    base_url: str
    status: ServerStatus = ServerStatus.ACTIVE
    created_at: datetime = field(default_factory=now)


@dataclass
class McpToolRecord:
    id: str
    server_id: str
    name: str
    description: str
    input_schema: dict[str, Any]
    synced_at: datetime = field(default_factory=now)


@dataclass
class AccessPolicyRecord:
    id: str
    server_id: str
    tenant_id: str
    allowed_tools: list[str] | None = None  # None = every tool on this server is allowed


@dataclass
class JsonRpcRequest:
    jsonrpc: str
    method: str
    params: dict[str, Any] | None
    id: str | int | None


@dataclass
class JsonRpcResponse:
    jsonrpc: str
    id: str | int | None
    result: Any | None = None
    error: dict[str, Any] | None = None
