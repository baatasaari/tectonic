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


class EvidencePackStatus(StrEnum):
    REQUESTED = "requested"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


class FrameworkProfileNotFoundError(Exception):
    def __init__(self, tenant_id: str, framework_name: str) -> None:
        super().__init__(f"framework profile not found for tenant={tenant_id} framework={framework_name}")


class EvidencePackNotFoundError(Exception):
    def __init__(self, pack_id: str) -> None:
        super().__init__(f"evidence pack not found: {pack_id}")


@dataclass
class FrameworkProfileRecord:
    id: str
    tenant_id: str
    framework_name: str
    version: str
    enabled: bool = True
    created_at: datetime = field(default_factory=now)


@dataclass
class ControlMappingRecord:
    id: str
    control_name: str
    framework_name: str
    framework_version: str
    clause_references: list[str]
    mapping_rationale: str
    deprecated: bool = False


@dataclass
class ControlImplementationEventRecord:
    id: str
    tenant_id: str
    control_name: str
    source_module: str
    evidence_ref: str
    occurred_at: datetime = field(default_factory=now)


@dataclass
class EvidencePackRecord:
    id: str
    tenant_id: str
    framework_name: str
    status: EvidencePackStatus = EvidencePackStatus.REQUESTED
    generated_at: datetime | None = None
    coverage_percentage: float = 0.0
    document_ref: str | None = None
    document_format: str = "pdf"
    document_bytes_b64: str | None = None
    created_at: datetime = field(default_factory=now)
    # Durable job-queue fields (LLD gap fix: generation used to run as a FastAPI
    # BackgroundTasks job, so a pod restart mid-generation lost the job forever with
    # the record stuck at status=generating). See core/evidence_worker.py.
    worker_id: str | None = None
    lease_expires_at: datetime | None = None
    attempts: int = 0
    last_error: str | None = None


@dataclass
class MappingResult:
    control_name: str
    framework_name: str
    clause_references: list[str]
