"""Framework-agnostic domain objects (LLD §3 "Data model": follows
OpenTelemetry's standard trace/span shape plus the platform-specific
extension attributes already named per-module, e.g. `workflow.step_id`,
`gen_ai.usage.input_tokens`, `llm_gateway.cost`).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


def now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid.uuid4())


class TraceNotFoundError(Exception):
    def __init__(self, trace_id: str) -> None:
        super().__init__(f"no spans recorded for trace: {trace_id}")


class SLONotFoundError(Exception):
    def __init__(self, slo_id: str) -> None:
        super().__init__(f"SLO not found: {slo_id}")


class AlertRuleNotFoundError(Exception):
    def __init__(self, rule_id: str) -> None:
        super().__init__(f"Alert rule not found: {rule_id}")


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


@dataclass
class TraceSummary:
    """One row of the trace *query* surface (`GET /traces`) -- a
    dashboard/support-engineer-facing rollup of a trace's spans,
    computed by a real aggregate query (`ObservabilityRepository.
    list_trace_summaries`), never by pulling every span client-side."""

    trace_id: str
    tenant_id: str
    workflow_type: str | None
    span_count: int
    start_time: datetime
    end_time: datetime
    has_error: bool

    @property
    def duration_seconds(self) -> float:
        return (self.end_time - self.start_time).total_seconds()


class SLOMetric(StrEnum):
    """The two metrics this module can actually compute from ingested
    span data alone -- never a third, fabricated one needing data this
    module doesn't have."""

    LATENCY_P95 = "latency_p95"
    ERROR_RATE = "error_rate"


class AlertComparison(StrEnum):
    GT = "gt"
    LT = "lt"


class AlertStatus(StrEnum):
    FIRING = "firing"
    RESOLVED = "resolved"


@dataclass
class SLODefinition:
    id: str
    tenant_id: str
    name: str
    metric: SLOMetric
    target: float
    window_hours: int
    # None == evaluated across every service this tenant has spans for; set ==
    # scoped to one service's own spans only.
    service_name: str | None = None
    created_at: datetime = field(default_factory=now)


@dataclass
class SLOEvaluationResult:
    """`current_value`/`compliant` are `None` together when the SLO's
    window has zero samples -- insufficient-data-over-fabrication, the
    same posture Billing and Metering's own `ComplianceReport` takes
    with zero active secrets: there is nothing to be compliant or
    non-compliant about, so this never reports a fabricated pass."""

    slo_id: str
    tenant_id: str
    metric: SLOMetric
    target: float
    sample_count: int
    current_value: float | None
    compliant: bool | None
    # Only meaningful for ERROR_RATE (the standard SRE "fraction of budget left"
    # formula); LATENCY_P95 compliance is a per-window pass/fail against a ceiling,
    # not a consumable budget, so it's always None there -- not fabricated.
    error_budget_remaining: float | None
    evaluated_at: datetime = field(default_factory=now)


@dataclass
class AlertRule:
    id: str
    tenant_id: str
    name: str
    metric: SLOMetric
    comparison: AlertComparison
    threshold: float
    window_hours: int
    service_name: str | None = None
    enabled: bool = True
    created_at: datetime = field(default_factory=now)


@dataclass
class AlertEvent:
    id: str
    rule_id: str
    tenant_id: str
    status: AlertStatus
    value: float
    threshold: float
    triggered_at: datetime = field(default_factory=now)
    resolved_at: datetime | None = None
