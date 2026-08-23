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


class DocumentStatus(StrEnum):
    ACTIVE = "active"
    STALE = "stale"
    ARCHIVED = "archived"


class SourceType(StrEnum):
    UPLOAD = "upload"
    SYNC = "sync"


class DocumentNotFoundError(Exception):
    def __init__(self, document_id: str) -> None:
        super().__init__(f"document not found: {document_id}")
        self.document_id = document_id


@dataclass
class DocumentRecord:
    id: str
    tenant_id: str
    title: str
    source_type: SourceType
    current_version_id: str | None = None
    status: DocumentStatus = DocumentStatus.ACTIVE
    staleness_threshold_days: int | None = None  # None = use tenant default
    last_reviewed_at: datetime = field(default_factory=now)
    created_at: datetime = field(default_factory=now)


@dataclass
class DocumentVersionRecord:
    id: str
    document_id: str
    content_hash: str
    blob_ref: str
    version_number: int
    created_by: str = ""
    created_at: datetime = field(default_factory=now)


@dataclass
class ChunkRecord:
    id: str
    document_version_id: str
    content: str
    chunk_index: int
    policy_tags: list[str] = field(default_factory=list)
    token_count: int = 0


@dataclass
class PolicyTagRecord:
    id: str
    tenant_id: str
    name: str
    description: str = ""


@dataclass
class IngestionResult:
    document: DocumentRecord
    version: DocumentVersionRecord
    chunk_count: int
