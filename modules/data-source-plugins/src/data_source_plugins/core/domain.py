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


class ConnectorStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"


class SyncRunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DRIFT_DETECTED = "drift_detected"
    AUTO_ADAPTED = "auto_adapted"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"
    PAUSED = "paused"


class DriftClassification(StrEnum):
    ADDITIVE = "additive"
    TYPE_WIDENING = "type_widening"
    BREAKING = "breaking"


class ConnectorNotFoundError(Exception):
    def __init__(self, connector_id: str) -> None:
        super().__init__(f"connector not found: {connector_id}")
        self.connector_id = connector_id


@dataclass
class ConnectorConfigRecord:
    id: str
    tenant_id: str
    source_type: str
    connection_config: dict[str, Any] = field(default_factory=dict)  # non-secret fields only
    secrets_ref: str = ""  # pointer to Secrets and Credential Management module
    sync_schedule: str | None = None
    status: ConnectorStatus = ConnectorStatus.ACTIVE
    created_at: datetime = field(default_factory=now)


@dataclass
class SchemaSnapshotRecord:
    id: str
    connector_id: str
    schema: dict[str, Any]
    version: int
    captured_at: datetime = field(default_factory=now)


@dataclass
class SyncRunRecord:
    id: str
    connector_id: str
    status: SyncRunStatus
    records_synced: int = 0
    started_at: datetime = field(default_factory=now)
    completed_at: datetime | None = None


@dataclass
class QualityScoreRecord:
    id: str
    connector_id: str
    sync_run_id: str
    completeness_score: float
    freshness_score: float
    format_validity_score: float
    overall_score: float
    computed_at: datetime = field(default_factory=now)


@dataclass
class DriftIncidentRecord:
    id: str
    connector_id: str
    schema_diff: dict[str, Any]
    classification: DriftClassification
    auto_adapted: bool
    resolved_by: str | None = None
    created_at: datetime = field(default_factory=now)


@dataclass
class DriftDetectionResult:
    drift_detected: bool
    schema_diff: dict[str, Any]
    classification: DriftClassification


@dataclass
class SyncOutcome:
    sync_run: SyncRunRecord
    drift_incident: DriftIncidentRecord | None
    quality_score: QualityScoreRecord | None
    normalised_record_count: int
