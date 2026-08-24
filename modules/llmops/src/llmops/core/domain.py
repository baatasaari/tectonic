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


class ModelVersionStatus(StrEnum):
    REGISTERED = "registered"
    CANARY = "canary"
    ACTIVE = "active"
    ROLLED_BACK = "rolled_back"
    SUPERSEDED = "superseded"


class DeploymentStage(StrEnum):
    CANARY = "canary"
    ACTIVE = "active"
    ROLLED_BACK = "rolled_back"
    SUPERSEDED = "superseded"


# The rollout state machine (LLD §Level 3 "The rollout state machine"): any transition
# not a value here is illegal and raises InvalidTransitionError.
_LEGAL_TRANSITIONS: dict[DeploymentStage, set[DeploymentStage]] = {
    DeploymentStage.CANARY: {DeploymentStage.ACTIVE, DeploymentStage.ROLLED_BACK},
    DeploymentStage.ACTIVE: {DeploymentStage.ROLLED_BACK, DeploymentStage.SUPERSEDED},
    DeploymentStage.ROLLED_BACK: set(),
    DeploymentStage.SUPERSEDED: set(),
}


def is_legal_transition(from_stage: DeploymentStage, to_stage: DeploymentStage) -> bool:
    return to_stage in _LEGAL_TRANSITIONS.get(from_stage, set())


class ModelVersionNotFoundError(Exception):
    def __init__(self, model_version_id: str) -> None:
        super().__init__(f"Model version not found: {model_version_id}")


class DeploymentNotFoundError(Exception):
    def __init__(self, deployment_id: str) -> None:
        super().__init__(f"Deployment not found: {deployment_id}")


class InvalidTransitionError(Exception):
    def __init__(self, from_stage: DeploymentStage, to_stage: DeploymentStage) -> None:
        super().__init__(f"Illegal transition: {from_stage.value} -> {to_stage.value}")
        self.from_stage = from_stage
        self.to_stage = to_stage


class CanaryGateFailedError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Canary gate did not pass: {reason}")
        self.reason = reason


class NoActiveVersionError(Exception):
    def __init__(self, model_name: str, target: str) -> None:
        super().__init__(f"No active version for model '{model_name}' on target '{target}'")


@dataclass
class ModelVersionRecord:
    id: str
    tenant_id: str
    model_name: str
    version: str
    artifact_ref: str
    status: ModelVersionStatus = ModelVersionStatus.REGISTERED
    created_at: datetime = field(default_factory=now)


@dataclass
class DeploymentRecord:
    id: str
    tenant_id: str
    model_version_id: str
    model_name: str
    target: str
    canary_percentage: int = 0
    stage: DeploymentStage = DeploymentStage.CANARY
    started_at: datetime = field(default_factory=now)
    promoted_at: datetime | None = None
    rolled_back_at: datetime | None = None
    rollback_reason: str | None = None
    created_at: datetime = field(default_factory=now)
    updated_at: datetime = field(default_factory=now)


@dataclass
class CanaryGateResult:
    sample_size: int
    pass_rate: float | None
    passed: bool
    reason: str
