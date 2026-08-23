"""Framework-agnostic domain objects for the execution engine.

The scheduler, router and executors work against these dataclasses rather
than SQLAlchemy models directly, so the same core logic runs unchanged
against the real Postgres-backed repository or an in-memory fake in unit
tests (LLD §4.8: "unit tests use in-memory fakes only").
"""
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


class InstanceStatus(StrEnum):
    RUNNING = "running"
    PAUSED_FOR_APPROVAL = "paused_for_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    TERMINATED = "terminated"


class StepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    REPLAN_TRIGGERED = "replan_triggered"


class ExecutionMode(StrEnum):
    SYMBOLIC = "symbolic"
    NEURAL = "neural"
    HUMAN = "human"
    AUTO = "auto"


class DefinitionStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMED_OUT = "timed_out"


@dataclass
class RetryPolicy:
    max_retries: int = 3
    backoff_strategy: str = "exponential"  # exponential|fixed|none
    compensation_step_id: str | None = None


@dataclass
class WorkflowNode:
    id: str
    type: str
    execution_mode: ExecutionMode
    confidence_threshold: float = 0.85
    config: dict[str, Any] = field(default_factory=dict)
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    timeout_seconds: int = 30


@dataclass
class WorkflowEdge:
    from_: str
    to: str
    condition: str | None = None


@dataclass
class WorkflowGraph:
    nodes: list[WorkflowNode]
    edges: list[WorkflowEdge]
    entry_point: str
    termination_points: list[str]

    def node(self, step_id: str) -> WorkflowNode:
        for n in self.nodes:
            if n.id == step_id:
                return n
        raise KeyError(step_id)

    def outgoing(self, step_id: str) -> list[WorkflowEdge]:
        return [e for e in self.edges if e.from_ == step_id]

    def incoming(self, step_id: str) -> list[WorkflowEdge]:
        return [e for e in self.edges if e.to == step_id]


@dataclass
class WorkflowDefinitionRecord:
    id: str
    name: str
    version: int
    status: DefinitionStatus
    graph_schema: dict
    tenant_id: str
    created_by: str
    created_at: datetime = field(default_factory=now)
    published_at: datetime | None = None


@dataclass
class WorkflowInstanceRecord:
    id: str
    definition_id: str
    definition_version: int
    tenant_id: str
    trace_id: str
    status: InstanceStatus = InstanceStatus.RUNNING
    current_step_ids: list[str] = field(default_factory=list)
    context: dict = field(default_factory=dict)
    started_at: datetime = field(default_factory=now)
    completed_at: datetime | None = None


@dataclass
class StepExecutionRecord:
    id: str
    instance_id: str
    step_id: str
    execution_mode: ExecutionMode
    status: StepStatus = StepStatus.PENDING
    input_snapshot: dict = field(default_factory=dict)
    output: dict | None = None
    confidence_score: float | None = None
    retry_count: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass
class ApprovalRequestRecord:
    id: str
    step_execution_id: str
    human_oversight_ref_id: str | None = None
    status: ApprovalStatus = ApprovalStatus.PENDING
    requested_at: datetime = field(default_factory=now)
    resolved_at: datetime | None = None


@dataclass
class StepOutcome:
    """Result of executing one step, returned by every step executor
    (symbolic/neural/human) to the scheduler."""

    status: StepStatus
    output: dict[str, Any] | None = None
    confidence_score: float | None = None
    error: str | None = None
    awaiting_approval_id: str | None = None


@dataclass
class ReplanEventRecord:
    id: str
    instance_id: str
    trigger_reason: str
    original_step_id: str
    new_graph_delta: dict
    created_at: datetime = field(default_factory=now)
