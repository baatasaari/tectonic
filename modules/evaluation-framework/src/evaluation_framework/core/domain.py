"""Framework-agnostic domain objects (LLD §3 data model)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


def now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid.uuid4())


class EvalRunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED_TO_EVALUATE = "failed_to_evaluate"


class EvalRunNotFoundError(Exception):
    def __init__(self, eval_run_id: str) -> None:
        super().__init__(f"eval run not found: {eval_run_id}")


@dataclass
class EvalRunRecord:
    id: str
    tenant_id: str
    trigger_source: str
    agent_ref: str
    metrics_evaluated: list[str] = field(default_factory=list)
    status: EvalRunStatus = EvalRunStatus.RUNNING
    started_at: datetime = field(default_factory=now)
    completed_at: datetime | None = None


@dataclass
class MetricScoreRecord:
    id: str
    eval_run_id: str
    tenant_id: str
    agent_ref: str
    metric_name: str
    score: float
    threshold: float
    passed: bool
    created_at: datetime = field(default_factory=now)


@dataclass
class GateResultRecord:
    id: str
    eval_run_id: str
    overall_passed: bool
    blocking_failures: list[str] = field(default_factory=list)
    environment: str = "production"
    created_at: datetime = field(default_factory=now)


@dataclass
class DomainMetricPackRecord:
    id: str
    tenant_id: str
    pack_name: str
    enabled: bool = True
    custom_thresholds: dict[str, float] = field(default_factory=dict)
