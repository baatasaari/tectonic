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


class IdentityType(StrEnum):
    USER = "user"
    AGENT = "agent"
    SERVICE = "service"


class IdentityStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"


# The identity lifecycle state machine (LLD §Level 3 "The identity lifecycle state
# machine"): any transition not a value here is illegal and raises
# InvalidTransitionError -- the same shape this platform's other state machines
# (Agent Marketplace, LLMOps, Deployment Strategy, PromptOps, Multi-tenancy) already
# established.
_LEGAL_TRANSITIONS: dict[IdentityStatus, set[IdentityStatus]] = {
    IdentityStatus.ACTIVE: {IdentityStatus.REVOKED},
    IdentityStatus.REVOKED: {IdentityStatus.ACTIVE},
}


def is_legal_transition(from_status: IdentityStatus, to_status: IdentityStatus) -> bool:
    return to_status in _LEGAL_TRANSITIONS.get(from_status, set())


class IdentityNotFoundError(Exception):
    def __init__(self, identity_id: str) -> None:
        super().__init__(f"Identity not found: {identity_id}")


class IdentityNotActiveError(Exception):
    def __init__(self, identity_id: str) -> None:
        super().__init__(f"Identity is not active: {identity_id}")


class RoleNotFoundError(Exception):
    def __init__(self, role_name: str) -> None:
        super().__init__(f"Role not found: {role_name}")


class InvalidTransitionError(Exception):
    def __init__(self, from_status: IdentityStatus, to_status: IdentityStatus) -> None:
        super().__init__(f"Illegal transition: {from_status.value} -> {to_status.value}")
        self.from_status = from_status
        self.to_status = to_status


@dataclass
class RoleRecord:
    name: str
    scopes: list[str] = field(default_factory=list)
    description: str = ""
    created_at: datetime = field(default_factory=now)


@dataclass
class IdentityRecord:
    id: str
    tenant_id: str
    name: str
    type: IdentityType = IdentityType.AGENT
    status: IdentityStatus = IdentityStatus.ACTIVE
    role_names: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=now)
    updated_at: datetime = field(default_factory=now)


@dataclass
class AuthDecisionRecord:
    id: str
    tenant_id: str
    identity_id: str
    required_scope: str
    allowed: bool
    reason: str
    checked_at: datetime = field(default_factory=now)


@dataclass
class IssuedToken:
    token: str
    granted_scopes: list[str]


@dataclass
class AuthDecisionResult:
    allowed: bool
    reason: str
