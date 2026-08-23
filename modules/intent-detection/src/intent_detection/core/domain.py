"""Framework-agnostic domain objects (LLD §3.1 data model)."""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


def now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid.uuid4())


def hash_input(text: str) -> str:
    """Privacy-by-design: raw input is never persisted, only a hash for
    dedup/analysis (LLD §3.1 ClassificationLog.input_hash)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class TaxonomyStatus(StrEnum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    DRAFT = "draft"


@dataclass
class IntentDefinition:
    name: str
    description: str = ""
    examples: list[str] = field(default_factory=list)


@dataclass
class IntentTaxonomyRecord:
    id: str
    tenant_id: str
    version: int
    intents: list[IntentDefinition]
    status: TaxonomyStatus = TaxonomyStatus.DRAFT
    created_at: datetime = field(default_factory=now)


@dataclass
class DetectedIntent:
    name: str
    confidence: float


@dataclass
class ClassificationLogRecord:
    id: str
    tenant_id: str
    input_hash: str
    taxonomy_version: int
    intents_detected: list[DetectedIntent]
    fallback_used: bool
    created_at: datetime = field(default_factory=now)


@dataclass
class DriftReportRecord:
    id: str
    tenant_id: str
    taxonomy_version: int
    drift_score: float
    flagged_intents: list[str]
    created_at: datetime = field(default_factory=now)


@dataclass
class ClassificationResult:
    intents: list[DetectedIntent]
    fallback_used: bool
    taxonomy_version: int


class TaxonomyNotFoundError(Exception):
    pass


class NoActiveTaxonomyError(Exception):
    pass
