"""Framework-agnostic domain objects (LLD §3 data model)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


def now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid.uuid4())


class ListingStatus(StrEnum):
    PENDING_REVIEW = "pending_review"
    PUBLISHED = "published"
    REJECTED = "rejected"
    DEPRECATED = "deprecated"


# The governance state machine (LLD §Level 3 "The governance state machine"):
# any transition not a value here is illegal and raises InvalidTransitionError.
_LEGAL_TRANSITIONS: dict[ListingStatus, set[ListingStatus]] = {
    ListingStatus.PENDING_REVIEW: {ListingStatus.PUBLISHED, ListingStatus.REJECTED},
    ListingStatus.PUBLISHED: {ListingStatus.DEPRECATED},
    ListingStatus.REJECTED: set(),
    ListingStatus.DEPRECATED: set(),
}


def is_legal_transition(from_status: ListingStatus, to_status: ListingStatus) -> bool:
    return to_status in _LEGAL_TRANSITIONS.get(from_status, set())


class ListingNotFoundError(Exception):
    def __init__(self, listing_id: str) -> None:
        super().__init__(f"Listing not found: {listing_id}")


class InvalidTransitionError(Exception):
    def __init__(self, from_status: ListingStatus, to_status: ListingStatus) -> None:
        super().__init__(f"Illegal transition: {from_status.value} -> {to_status.value}")
        self.from_status = from_status
        self.to_status = to_status


class AgentCardNotFoundError(Exception):
    def __init__(self, agent_card_id: str) -> None:
        super().__init__(f"Agent Card not found: {agent_card_id}")


@dataclass
class ListingRecord:
    id: str
    tenant_id: str
    agent_card_id: str
    name: str
    description: str
    skills_snapshot: list[dict[str, Any]] = field(default_factory=list)
    trust_score_snapshot: float | None = None
    status: ListingStatus = ListingStatus.PENDING_REVIEW
    submitted_by: str = ""
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    rejection_reason: str | None = None
    reuse_count: int = 0
    external_listing_enabled: bool = False
    created_at: datetime = field(default_factory=now)
    updated_at: datetime = field(default_factory=now)


@dataclass
class UsageEventRecord:
    id: str
    listing_id: str
    consumer_tenant_id: str
    used_at: datetime = field(default_factory=now)


@dataclass
class ReuseMetrics:
    reuse_count: int
    distinct_consumer_tenants: int
