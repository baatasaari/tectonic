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


class TenantStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELETED = "deleted"


# The tenant lifecycle state machine (LLD §Level 3 "The tenant lifecycle state
# machine"): any transition not a value here is illegal and raises
# InvalidTransitionError -- the same shape Agent Marketplace, LLMOps, Deployment
# Strategy and PromptOps already established.
_LEGAL_TRANSITIONS: dict[TenantStatus, set[TenantStatus]] = {
    TenantStatus.ACTIVE: {TenantStatus.SUSPENDED, TenantStatus.DELETED},
    TenantStatus.SUSPENDED: {TenantStatus.ACTIVE, TenantStatus.DELETED},
    TenantStatus.DELETED: set(),
}


def is_legal_transition(from_status: TenantStatus, to_status: TenantStatus) -> bool:
    return to_status in _LEGAL_TRANSITIONS.get(from_status, set())


class TenantNotFoundError(Exception):
    def __init__(self, tenant_id: str) -> None:
        super().__init__(f"Tenant not found: {tenant_id}")


class InvalidTransitionError(Exception):
    def __init__(self, from_status: TenantStatus, to_status: TenantStatus) -> None:
        super().__init__(f"Illegal transition: {from_status.value} -> {to_status.value}")
        self.from_status = from_status
        self.to_status = to_status


class ProbeTargetNotFoundError(Exception):
    def __init__(self, target_name: str) -> None:
        super().__init__(f"Unknown isolation probe target: {target_name}")


@dataclass
class TenantRecord:
    id: str
    name: str
    status: TenantStatus = TenantStatus.ACTIVE
    tier: str = "standard"
    created_at: datetime = field(default_factory=now)
    updated_at: datetime = field(default_factory=now)


@dataclass
class IsolationProbeResult:
    id: str
    tenant_id: str
    target_name: str
    passed: bool
    breach_count: int
    sample_size: int
    details: str
    checked_at: datetime = field(default_factory=now)


@dataclass
class TenantGateResult:
    allowed: bool
    reason: str
