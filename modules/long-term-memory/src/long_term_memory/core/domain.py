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


class MemoryItemNotFoundError(Exception):
    def __init__(self, item_id: str) -> None:
        super().__init__(f"memory item not found: {item_id}")


class DeletionRecordNotFoundError(Exception):
    def __init__(self, deletion_id: str) -> None:
        super().__init__(f"deletion record not found: {deletion_id}")


@dataclass
class MemoryItemRecord:
    id: str
    tenant_id: str
    scope: str
    memory_type: MemoryType
    content: str
    visibility_policy_ref: str = ""
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
