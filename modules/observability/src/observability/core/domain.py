"""Framework-agnostic domain objects (LLD §3 "Data model": follows
OpenTelemetry's standard trace/span shape plus the platform-specific
extension attributes already named per-module, e.g. `workflow.step_id`,
`gen_ai.usage.input_tokens`, `llm_gateway.cost`).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


def now() -> datetime:
    return datetime.now(UTC)


class TraceNotFoundError(Exception):
    def __init__(self, trace_id: str) -> None:
        super().__init__(f"no spans recorded for trace: {trace_id}")


@dataclass
class SpanRecord:
    id: str
    tenant_id: str
    trace_id: str
    span_id: str
    parent_span_id: str | None
    name: str
    service_name: str
    start_time: datetime
    end_time: datetime
    attributes: dict = field(default_factory=dict)
    status: str = "ok"
    workflow_type: str | None = None
    ingested_at: datetime = field(default_factory=now)

    @property
    def duration_seconds(self) -> float:
        return (self.end_time - self.start_time).total_seconds()


@dataclass
class CostAttributionEntry:
    span_id: str
    name: str
    duration_seconds: float
    input_tokens: int
    output_tokens: int
    cost_usd: float


@dataclass
class TraceCompletenessResult:
    tenant_id: str
    completeness_ratio: float
    traces_checked: int
    traces_with_known_shape: int
