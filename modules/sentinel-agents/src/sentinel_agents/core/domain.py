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


class AlertType(StrEnum):
    SINGLE_AGENT = "single_agent"
    SWARM = "swarm"


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AlertStatus(StrEnum):
    DETECTED = "detected"
    ALERTED = "alerted"
    AUTONOMOUS_INTERVENTION = "autonomous_intervention"
    ESCALATED_TO_HUMAN = "escalated_to_human"
    RESOLVED = "resolved"
    DISMISSED_FALSE_POSITIVE = "dismissed_false_positive"


class InterventionType(StrEnum):
    ALERT_ONLY = "alert_only"
    PAUSE = "pause"
    TERMINATE = "terminate"
    CIRCUIT_BREAK = "circuit_break"


class AlertNotFoundError(Exception):
    def __init__(self, alert_id: str) -> None:
        super().__init__(f"alert not found: {alert_id}")


@dataclass
class AgentActionEvent:
    tenant_id: str
    agent_ref: str
    action_type: str
    value: float
    instance_id: str | None = None  # Workflow Engine instance this action belongs to, if any
    timestamp: datetime = field(default_factory=now)


@dataclass
class AgentBaselineRecord:
    agent_ref: str
    action_type: str
    mean: float = 0.0
    m2: float = 0.0  # Welford running sum of squared deviations
    sample_count: int = 0
    last_updated_at: datetime = field(default_factory=now)

    @property
    def variance(self) -> float:
        return self.m2 / self.sample_count if self.sample_count > 0 else 0.0


@dataclass
class AlertRecord:
    id: str
    tenant_id: str
    alert_type: AlertType
    agent_refs: list[str]
    severity: Severity
    description: str
    status: AlertStatus = AlertStatus.DETECTED
    detected_at: datetime = field(default_factory=now)


@dataclass
class InterventionRecord:
    id: str
    alert_id: str
    intervention_type: InterventionType
    target_ref: str
    outcome: str
    executed_at: datetime = field(default_factory=now)


@dataclass
class SwarmCorrelationWindowRecord:
    id: str
    tenant_id: str
    window_start: datetime
    window_end: datetime
    agent_refs_involved: list[str]
    correlation_score: float
    pattern_description: str
