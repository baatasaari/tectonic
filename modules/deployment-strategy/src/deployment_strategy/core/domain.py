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


class DeploymentStage(StrEnum):
    CANARY = "canary"
    ACTIVE = "active"
    ROLLED_BACK = "rolled_back"
    SUPERSEDED = "superseded"


# The rollout state machine (LLD §Level 3 "The rollout state machine"): any transition
# not a value here is illegal and raises InvalidTransitionError -- the identical shape
# Agent Marketplace (Module 24) and LLMOps (Module 25) already established.
_LEGAL_TRANSITIONS: dict[DeploymentStage, set[DeploymentStage]] = {
    DeploymentStage.CANARY: {DeploymentStage.ACTIVE, DeploymentStage.ROLLED_BACK},
    DeploymentStage.ACTIVE: {DeploymentStage.ROLLED_BACK, DeploymentStage.SUPERSEDED},
    DeploymentStage.ROLLED_BACK: set(),
    DeploymentStage.SUPERSEDED: set(),
}


def is_legal_transition(from_stage: DeploymentStage, to_stage: DeploymentStage) -> bool:
    return to_stage in _LEGAL_TRANSITIONS.get(from_stage, set())


class DeploymentNotFoundError(Exception):
    def __init__(self, deployment_id: str) -> None:
        super().__init__(f"Deployment not found: {deployment_id}")


class InvalidTransitionError(Exception):
    def __init__(self, from_stage: DeploymentStage, to_stage: DeploymentStage) -> None:
        super().__init__(f"Illegal transition: {from_stage.value} -> {to_stage.value}")
        self.from_stage = from_stage
        self.to_stage = to_stage


class CanaryHealthCheckFailedError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Canary health check did not pass: {reason}")
        self.reason = reason


class NoActiveDeploymentError(Exception):
    def __init__(self, service_name: str, target: str) -> None:
        super().__init__(f"No active deployment for service '{service_name}' on target '{target}'")


@dataclass
class DeploymentRecord:
    id: str
    tenant_id: str
    service_name: str
    build_ref: str
    target: str
    canary_percentage: int = 10
    # Optional: which FinOps budget policy this deployment's cost health should be
    # checked against. FinOps has no "list budget policies for a tenant" endpoint (by
    # design -- see that module's LLD), so this is supplied by the caller at deploy time
    # rather than discovered; left unset, the cost signal is simply excluded from the
    # health check, not treated as a failure.
    budget_policy_id: str | None = None
    stage: DeploymentStage = DeploymentStage.CANARY
    started_at: datetime = field(default_factory=now)
    promoted_at: datetime | None = None
    rolled_back_at: datetime | None = None
    rollback_reason: str | None = None
    created_at: datetime = field(default_factory=now)
    updated_at: datetime = field(default_factory=now)


@dataclass
class CanaryHealthResult:
    groundedness_score: float | None
    cost_score: float | None
    composite_score: float | None
    passed: bool
    reason: str
