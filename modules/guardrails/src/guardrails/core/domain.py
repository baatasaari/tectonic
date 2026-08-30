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


class CheckStage(StrEnum):
    INPUT = "input"
    OUTPUT = "output"


class Decision(StrEnum):
    ALLOW = "allow"
    BLOCK = "block"
    REDACT = "redact"


class PolicyProfileNotFoundError(Exception):
    def __init__(self, profile_id: str) -> None:
        super().__init__(f"policy profile not found: {profile_id}")


@dataclass
class PolicyProfileRecord:
    id: str
    tenant_id: str
    name: str
    enabled_checks: list[str] = field(default_factory=lambda: ["pii_detection", "jailbreak_detection", "groundedness_check"])
    pii_entity_types: list[str] = field(default_factory=lambda: ["EMAIL", "PHONE_NUMBER", "PERSON", "CREDIT_CARD"])
    denied_topics: list[str] = field(default_factory=list)
    groundedness_threshold: float = 0.85
    status: str = "active"
    created_at: datetime = field(default_factory=now)


@dataclass
class InterventionLogRecord:
    id: str
    tenant_id: str
    policy_profile_id: str
    stage: CheckStage
    check_type: str
    decision: Decision
    violation_category: str | None
    latency_ms: float
    created_at: datetime = field(default_factory=now)


@dataclass
class BypassIncidentRecord:
    id: str
    red_team_run_id: str
    attack_pattern: str
    target_check: str
    severity: str = "high"
    resolved: bool = False


@dataclass
class RedTeamRunRecord:
    id: str
    tenant_id: str
    attempts_generated: int
    successful_bypasses: int
    run_at: datetime = field(default_factory=now)


@dataclass
class CheckResult:
    decision: Decision
    violation_category: str | None
    redacted_text: str | None
    checks_run: list[str] = field(default_factory=list)
