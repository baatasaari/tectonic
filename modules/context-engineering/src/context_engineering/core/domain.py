"""Framework-agnostic domain objects (LLD §3.1 data model)."""
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


class ItemDisposition(StrEnum):
    INCLUDED = "included"
    SUMMARISED = "summarised"
    DROPPED = "dropped"


@dataclass
class CandidateItem:
    source: str  # e.g. "agentic_rag", "short_term_memory", "long_term_memory", "workflow_context"
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    # metadata may carry: role, entity_type, policy_tags (list[str])


@dataclass
class TaggedItem:
    candidate: CandidateItem
    role_match: bool
    entity_type_match: bool
    matched_policy_tags: list[str] = field(default_factory=list)


@dataclass
class RankedItem:
    tagged: TaggedItem
    priority_score: float


@dataclass
class AssembledItem:
    source: str
    content: str
    tokens: int
    disposition: ItemDisposition


@dataclass
class OntologyConfigRecord:
    id: str
    tenant_id: str
    version: int
    roles: list[str] = field(default_factory=list)
    entity_types: list[str] = field(default_factory=list)
    policy_tags: list[str] = field(default_factory=list)


@dataclass
class PrioritisationWeightsRecord:
    id: str
    tenant_id: str
    task_type: str
    feature_weights: dict[str, float] = field(default_factory=dict)
    last_updated_at: datetime = field(default_factory=now)


@dataclass
class ContextAssemblyRecord:
    id: str
    request_ref: str
    task_type: str
    items_included: list[AssembledItem]
    items_dropped: list[AssembledItem]
    items_summarised: list[AssembledItem]
    total_tokens_used: int
    created_at: datetime = field(default_factory=now)


@dataclass
class AssemblyResult:
    assembled_context: str
    tokens_used: int
    items_included_count: int
    items_dropped_count: int
    items_summarised_count: int
