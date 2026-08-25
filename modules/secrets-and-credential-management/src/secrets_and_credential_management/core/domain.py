"""Framework-agnostic domain objects (LLD §3 data model)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum


def now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid.uuid4())


class SecretStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"


# The secret lifecycle state machine: any transition not a value here is illegal and
# raises InvalidTransitionError -- the same shape this platform's other state machines
# (Agent Marketplace, LLMOps, Deployment Strategy, PromptOps, Multi-tenancy, Identity
# and Access) already established.
_LEGAL_TRANSITIONS: dict[SecretStatus, set[SecretStatus]] = {
    SecretStatus.ACTIVE: {SecretStatus.REVOKED},
    SecretStatus.REVOKED: set(),
}


def is_legal_transition(from_status: SecretStatus, to_status: SecretStatus) -> bool:
    return to_status in _LEGAL_TRANSITIONS.get(from_status, set())


class SecretNotFoundError(Exception):
    def __init__(self, secret_id: str) -> None:
        super().__init__(f"Secret not found: {secret_id}")


class SecretRevokedError(Exception):
    def __init__(self, secret_id: str) -> None:
        super().__init__(f"Secret is revoked: {secret_id}")


class AccessDeniedError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Access denied: {reason}")
        self.reason = reason


class InvalidTransitionError(Exception):
    def __init__(self, from_status: SecretStatus, to_status: SecretStatus) -> None:
        super().__init__(f"Illegal transition: {from_status.value} -> {to_status.value}")
        self.from_status = from_status
        self.to_status = to_status


@dataclass
class SecretRecord:
    id: str
    tenant_id: str
    namespace: str
    key_name: str
    status: SecretStatus = SecretStatus.ACTIVE
    rotation_interval_days: int = 90
    last_rotated_at: datetime = field(default_factory=now)
    next_rotation_due_at: datetime = field(default_factory=lambda: now() + timedelta(days=90))
    current_version: int = 1
    created_at: datetime = field(default_factory=now)
    updated_at: datetime = field(default_factory=now)


@dataclass
class SecretVersionRecord:
    id: str
    secret_id: str
    version: int
    ciphertext: str
    created_at: datetime = field(default_factory=now)


@dataclass
class SecretAccessRecord:
    id: str
    secret_id: str
    tenant_id: str
    allowed: bool
    reason: str
    accessed_at: datetime = field(default_factory=now)


@dataclass
class ComplianceReport:
    tenant_id: str | None
    total_active: int
    overdue: int
    compliance_rate: float | None


@dataclass
class SecretAccessResult:
    """What `SecretAccessService.retrieve` returns: `value` is populated
    only when `allowed` is true -- a denial (or a not-yet-authorized
    caller) must never see a plaintext value alongside its `reason`."""

    allowed: bool
    reason: str
    value: str | None = None
