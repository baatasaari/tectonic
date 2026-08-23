"""Framework-agnostic domain objects (LLD §3.1 data model)."""
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


class ToolStatus(StrEnum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    PENDING_REVIEW = "pending_review"
    REJECTED = "rejected"


class InvocationStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED_CIRCUIT_OPEN = "rejected_circuit_open"


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class ToolDefinitionRecord:
    id: str
    tenant_id: str
    name: str
    mcp_server_ref: str
    schema: dict[str, Any] = field(default_factory=dict)
    status: ToolStatus = ToolStatus.ACTIVE
    synthesised: bool = False
    created_at: datetime = field(default_factory=now)


@dataclass
class ToolInvocationRecord:
    id: str
    tool_id: str
    agent_ref: str
    workflow_instance_id: str | None = None
    status: InvocationStatus = InvocationStatus.PENDING
    retry_count: int = 0
    latency_ms: float = 0.0
    created_at: datetime = field(default_factory=now)


@dataclass
class ReliabilityScoreRecord:
    tool_id: str
    rolling_success_rate: float = 1.0
    rolling_avg_latency_ms: float = 0.0
    last_updated_at: datetime = field(default_factory=now)


@dataclass
class CircuitBreakerStateRecord:
    tool_id: str
    state: CircuitState = CircuitState.CLOSED
    opened_at: datetime | None = None
    next_retry_at: datetime | None = None


@dataclass
class InvocationOutcome:
    status: InvocationStatus
    output: dict[str, Any] | None
    error: str | None
    retry_count: int
    latency_ms: float


class ToolNotFoundError(Exception):
    pass


class ToolNotActiveError(Exception):
    pass


class CircuitOpenError(Exception):
    def __init__(self, tool_id: str, retry_after: datetime | None):
        self.tool_id = tool_id
        self.retry_after = retry_after
        super().__init__(f"circuit open for tool '{tool_id}'")


class ToolCallError(Exception):
    def __init__(self, tool_id: str, message: str):
        self.tool_id = tool_id
        super().__init__(f"{tool_id}: {message}")


class SynthesisRejectedError(Exception):
    pass
