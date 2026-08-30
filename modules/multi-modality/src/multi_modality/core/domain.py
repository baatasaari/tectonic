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


class Modality(StrEnum):
    TEXT = "text"
    VOICE = "voice"
    IMAGE = "image"
    DOCUMENT = "document"


class GroundednessDecision(StrEnum):
    ALLOW = "allow"
    BLOCK = "block"
    REDACT = "redact"
    # No grounding_context was supplied -- the gate wasn't run at all, distinct from a
    # real "allow" verdict.
    NOT_CHECKED = "not_checked"
    # A grounding_context was supplied but Guardrails couldn't be reached -- the
    # extraction is still returned to the caller, just unverified, rather than failing
    # the whole request over one unavailable peer.
    UNAVAILABLE = "unavailable"


class ExtractionNotFoundError(Exception):
    def __init__(self, extraction_id: str) -> None:
        super().__init__(f"Extraction not found: {extraction_id}")


@dataclass
class ExtractionRecord:
    id: str
    tenant_id: str
    modality: Modality
    raw_content: str
    extracted_content: str
    grounding_context: str | None = None
    groundedness_decision: GroundednessDecision = GroundednessDecision.NOT_CHECKED
    groundedness_violation_category: str | None = None
    latency_ms: float = 0.0
    created_at: datetime = field(default_factory=now)
