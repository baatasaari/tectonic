"""Framework-agnostic domain objects (LLD §3 data model)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any


def now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid.uuid4())


class RequestStatus(StrEnum):
    PENDING = "pending"
    CLAIMED = "claimed"
    DECIDED = "decided"
    EXPIRED = "expired"


class DecisionType(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    OVERRIDE = "override"


class RequestNotFoundError(Exception):
    def __init__(self, request_id: str) -> None:
        super().__init__(f"oversight request not found: {request_id}")


class RequestNotClaimableError(Exception):
    def __init__(self, request_id: str, status: str) -> None:
        super().__init__(f"request {request_id} cannot be claimed in status {status}")


class RequestNotDecidableError(Exception):
    def __init__(self, request_id: str, status: str) -> None:
        super().__init__(f"request {request_id} cannot be decided in status {status}")


@dataclass
class OversightRequestRecord:
    id: str
    tenant_id: str
    requesting_module: str
    requesting_ref: str
    context: dict[str, Any] = field(default_factory=dict)
    priority: str = "medium"
    status: RequestStatus = RequestStatus.PENDING
    claimed_by: str | None = None
    created_at: datetime = field(default_factory=now)
    expires_at: datetime = field(default_factory=lambda: now() + timedelta(seconds=86400))


@dataclass
class DecisionRecord:
    id: str
    request_id: str
    decision: DecisionType
    decided_by: str
    decision_reason: str = ""
    decided_at: datetime = field(default_factory=now)


@dataclass
class OverrideRecord:
    id: str
    decision_id: str
    original_agent_proposal: dict[str, Any] = field(default_factory=dict)
    human_override_action: dict[str, Any] = field(default_factory=dict)
    override_reason: str = ""
    created_at: datetime = field(default_factory=now)


@dataclass
class NotificationLogRecord:
    id: str
    request_id: str
    channel: str
    delivered_at: datetime | None
    delivery_status: str
