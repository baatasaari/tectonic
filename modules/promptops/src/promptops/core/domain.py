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


class PromptVersionStatus(StrEnum):
    DRAFT = "draft"
    TESTING = "testing"
    ACTIVE = "active"
    ARCHIVED = "archived"


class ABTestStatus(StrEnum):
    RUNNING = "running"
    CONCLUDED = "concluded"


# The prompt version state machine (LLD §Level 3 "The version state machine"): any
# transition not a value here is illegal and raises InvalidTransitionError -- the same
# shape Agent Marketplace, LLMOps and Deployment Strategy already established.
_LEGAL_TRANSITIONS: dict[PromptVersionStatus, set[PromptVersionStatus]] = {
    PromptVersionStatus.DRAFT: {PromptVersionStatus.TESTING, PromptVersionStatus.ARCHIVED},
    PromptVersionStatus.TESTING: {PromptVersionStatus.ACTIVE, PromptVersionStatus.ARCHIVED},
    PromptVersionStatus.ACTIVE: {PromptVersionStatus.ARCHIVED},
    PromptVersionStatus.ARCHIVED: set(),
}


def is_legal_transition(from_status: PromptVersionStatus, to_status: PromptVersionStatus) -> bool:
    return to_status in _LEGAL_TRANSITIONS.get(from_status, set())


class PromptVersionNotFoundError(Exception):
    def __init__(self, prompt_version_id: str) -> None:
        super().__init__(f"Prompt version not found: {prompt_version_id}")


class ABTestNotFoundError(Exception):
    def __init__(self, ab_test_id: str) -> None:
        super().__init__(f"A/B test not found: {ab_test_id}")


class InvalidTransitionError(Exception):
    def __init__(self, from_status: PromptVersionStatus, to_status: PromptVersionStatus) -> None:
        super().__init__(f"Illegal transition: {from_status.value} -> {to_status.value}")
        self.from_status = from_status
        self.to_status = to_status


class ABTestNotConclusiveError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(f"A/B test is not yet conclusive: {reason}")
        self.reason = reason


class NoActivePromptVersionError(Exception):
    def __init__(self, prompt_name: str) -> None:
        super().__init__(f"No active prompt version for '{prompt_name}'")


@dataclass
class PromptVersionRecord:
    id: str
    tenant_id: str
    prompt_name: str
    version: str
    template: str
    status: PromptVersionStatus = PromptVersionStatus.DRAFT
    parent_version_id: str | None = None
    promoted_pass_rate: float | None = None
    promoted_sample_size: int | None = None
    created_at: datetime = field(default_factory=now)
    updated_at: datetime = field(default_factory=now)


@dataclass
class ABTestRecord:
    id: str
    tenant_id: str
    prompt_name: str
    version_a_id: str
    version_b_id: str
    status: ABTestStatus = ABTestStatus.RUNNING
    winner_version_id: str | None = None
    p_value: float | None = None
    sample_size_a: int = 0
    sample_size_b: int = 0
    started_at: datetime = field(default_factory=now)
    concluded_at: datetime | None = None


@dataclass
class ABTestResult:
    sample_size_a: int
    sample_size_b: int
    pass_rate_a: float | None
    pass_rate_b: float | None
    p_value: float | None
    significant: bool
    winner_version_id: str | None
    reason: str


@dataclass
class DriftCheckResult:
    baseline_pass_rate: float | None
    current_pass_rate: float | None
    current_sample_size: int
    p_value: float | None
    drifted: bool
    reason: str
