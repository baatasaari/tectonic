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


class RetrievalOutcome(StrEnum):
    SUFFICIENT = "sufficient"
    MAX_HOPS_REACHED = "max_hops_reached"


class RetrievalSource(StrEnum):
    VECTOR_DB = "vector_db"
    GRAPH_DB = "graph_db"
    KNOWLEDGE_BASE = "knowledge_base"


@dataclass
class Provenance:
    source_document: str
    version: str = "latest"
    location: str = ""


@dataclass
class RetrievedItem:
    content: str
    source: RetrievalSource
    provenance: Provenance
    retrieval_score: float = 0.0


@dataclass
class RetrievalRequestRecord:
    id: str
    tenant_id: str
    query: str
    scope: list[str] = field(default_factory=list)
    max_hops: int = 3
    groundedness_threshold: float = 0.85
    created_at: datetime = field(default_factory=now)


@dataclass
class RetrievalHopRecord:
    id: str
    request_id: str
    hop_number: int
    retrieved_items: list[RetrievedItem]
    groundedness_score: float
    reformulated_query: str | None = None
    created_at: datetime = field(default_factory=now)


@dataclass
class RetrievalResultRecord:
    request_id: str
    final_context: str
    total_hops: int
    final_groundedness_score: float
    provenance_chain: list[Provenance]
    outcome: RetrievalOutcome


@dataclass
class GroundednessAssessment:
    score: float
    gaps: str = ""


class NoRetrievalResultsError(Exception):
    pass
