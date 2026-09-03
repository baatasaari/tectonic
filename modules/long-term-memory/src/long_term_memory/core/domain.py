"""Framework-agnostic domain objects (LLD §3.1 data model)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


def now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid.uuid4())


class MemoryType(StrEnum):
    FACT = "fact"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"


class MemoryItemStatus(StrEnum):
    ACTIVE = "active"
    CONSOLIDATED = "consolidated"
    DECAYED = "decayed"
    DELETED = "deleted"


class ConsentBasis(StrEnum):
    """GDPR Art. 6-shaped lawful bases -- real, named categories rather
    than a bare boolean "has consent", since which basis applies changes
    what revoking it actually means (e.g. LEGAL_OBLIGATION can't be
    revoked by the subject the way EXPLICIT can)."""

    EXPLICIT = "explicit"
    LEGITIMATE_INTEREST = "legitimate_interest"
    CONTRACT = "contract"
    LEGAL_OBLIGATION = "legal_obligation"


class MemoryItemNotFoundError(Exception):
    def __init__(self, item_id: str) -> None:
        super().__init__(f"memory item not found: {item_id}")


class DeletionRecordNotFoundError(Exception):
    def __init__(self, deletion_id: str) -> None:
        super().__init__(f"deletion record not found: {deletion_id}")


class LegalHoldActiveError(Exception):
    """Raised when an erasure request targets a scope under an active
    legal hold -- ForgettingEngine.execute must refuse, not silently
    skip or silently delete anyway. See LegalHoldRecord's own
    docstring."""

    def __init__(self, scope: str, hold_id: str) -> None:
        super().__init__(f"scope {scope!r} is under active legal hold {hold_id!r}; erasure refused")
        self.scope = scope
        self.hold_id = hold_id


class ConsentRecordNotFoundError(Exception):
    def __init__(self, consent_id: str) -> None:
        super().__init__(f"consent record not found: {consent_id}")


class LegalHoldNotFoundError(Exception):
    def __init__(self, hold_id: str) -> None:
        super().__init__(f"legal hold not found: {hold_id}")


@dataclass
class MemoryItemRecord:
    id: str
    tenant_id: str
    scope: str
    memory_type: MemoryType
    content: str
    visibility_policy_ref: str = ""
    # Memory governance (independent architecture assessment's own "memory
    # governance" finding, previously zero coverage): what this item was
    # collected for. Purely recorded metadata at store time -- nothing
    # currently calls POST /items from another module (per Conversational
    # Engine's own README, "Long-Term Memory write-back" is still a
    # separately-scoped gap), so there is no existing caller to force a
    # required field or a hard consent check onto; MemoryService.query
    # is where this pairs with ConsentRecord to have a real effect. See
    # core/memory_service.py's own docstring on the consent-at-query
    # check for the full reasoning.
    purpose: str = ""
    vector_ref: str | None = None
    graph_ref: str | None = None
    status: MemoryItemStatus = MemoryItemStatus.ACTIVE
    relevance_score: float = 1.0
    created_at: datetime = field(default_factory=now)
    last_accessed_at: datetime = field(default_factory=now)


@dataclass
class ConsolidationRunRecord:
    id: str
    tenant_id: str
    items_merged_count: int = 0
    items_decayed_count: int = 0
    run_at: datetime = field(default_factory=now)


@dataclass
class ReflectionEntryRecord:
    id: str
    tenant_id: str
    agent_ref: str
    triggering_interaction_ref: str
    reflection_content: str
    applied: bool = False
    created_at: datetime = field(default_factory=now)


@dataclass
class DeletionRecord:
    id: str
    tenant_id: str
    subject_ref: str
    memory_items_deleted: list[str] = field(default_factory=list)
    deletion_proof_hash: str = ""
    requested_by: str = ""
    completed_at: datetime | None = None


@dataclass
class RankedMemoryItem:
    item: MemoryItemRecord
    score: float


@dataclass
class ConsentRecord:
    """A consent grant for (tenant_id, scope, purpose) -- one row per
    grant, revoked in place (revoked_at set on this same row, not a
    second row), the same "materialized view + event log" shape this
    platform already uses for Identity and Access's RoleBindingRecord.
    `MemoryService.query` treats a MemoryItemRecord whose `purpose` has
    no currently-active ConsentRecord covering (scope, purpose) as
    unavailable for retrieval -- see that method's own docstring."""

    id: str
    tenant_id: str
    scope: str
    purpose: str
    basis: ConsentBasis
    granted_by: str = ""
    granted_at: datetime = field(default_factory=now)
    revoked_at: datetime | None = None


@dataclass
class LegalHoldRecord:
    """A legal hold on (tenant_id, scope) -- while active (released_at is
    None), ForgettingEngine.execute must refuse an erasure request
    targeting this scope outright (raising LegalHoldActiveError, mapped
    to a 409), not silently skip the held items or silently delete them
    anyway. This is the one piece of "memory governance" with real
    teeth: a hold that doesn't actually block deletion isn't a hold."""

    id: str
    tenant_id: str
    scope: str
    reason: str
    placed_by: str = ""
    placed_at: datetime = field(default_factory=now)
    released_at: datetime | None = None
