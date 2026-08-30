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


class AuditPackStatus(StrEnum):
    REQUESTED = "requested"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


class AuditPackNotFoundError(Exception):
    def __init__(self, pack_id: str) -> None:
        super().__init__(f"audit pack not found: {pack_id}")


class InvalidNLQueryFilterError(Exception):
    """Raised when the NL Query Translator's LLM Gateway call produces a
    filter that doesn't validate against this module's own filter schema —
    a hallucinated field name or malformed value is surfaced as an error,
    never silently dropped or guessed past."""


@dataclass
class AuditEventRecord:
    id: str
    tenant_id: str
    source_module: str
    event_type: str
    payload: dict[str, Any]
    sequence_number: int
    entry_hash: str
    prev_hash: str | None = None
    occurred_at: datetime = field(default_factory=now)


@dataclass
class AuditEventFilter:
    """The one filter shape both the REST `GET /events` endpoint and the NL
    Query Translator's output are validated against — a translated query
    can misfilter but can never reach the repository as anything but this
    same, already-parameterized shape."""

    tenant_id: str
    event_type: str | None = None
    source_module: str | None = None
    control_name: str | None = None
    occurred_after: datetime | None = None
    occurred_before: datetime | None = None
    limit: int = 50
    offset: int = 0


@dataclass
class ChainVerificationResult:
    valid: bool
    verified_count: int
    break_at_sequence: int | None = None


@dataclass
class AuditPackRecord:
    id: str
    tenant_id: str
    status: AuditPackStatus = AuditPackStatus.REQUESTED
    filter_event_type: str | None = None
    filter_source_module: str | None = None
    filter_control_name: str | None = None
    filter_occurred_after: datetime | None = None
    filter_occurred_before: datetime | None = None
    event_count: int = 0
    chain_valid: bool | None = None
    generated_at: datetime | None = None
    document_ref: str | None = None
    document_format: str = "pdf"
    document_bytes_b64: str | None = None
    created_at: datetime = field(default_factory=now)
    # Durable job-queue fields, same design as Module 17's evidence-pack worker
    # (core/audit_pack_worker.py) — a pod restart mid-generation must not lose the job.
    worker_id: str | None = None
    lease_expires_at: datetime | None = None
    attempts: int = 0
    last_error: str | None = None
