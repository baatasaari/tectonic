"""Framework-agnostic domain objects (LLD §3 "Data model (Qdrant collection
schema, not a separate relational model)"). The Migration Manager's own
bookkeeping (`MigrationRecord`) is this module's one piece of state the
LLD's data model table doesn't name explicitly — see the module README's
"Design notes vs. the LLD".
"""
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


class MigrationStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class PointNotFoundError(Exception):
    def __init__(self, point_id: str) -> None:
        super().__init__(f"point not found: {point_id}")


class MigrationNotFoundError(Exception):
    def __init__(self, migration_id: str) -> None:
        super().__init__(f"migration not found: {migration_id}")


@dataclass
class SparseVectorData:
    indices: list[int] = field(default_factory=list)
    values: list[float] = field(default_factory=list)


@dataclass
class ScoredPointResult:
    id: str
    score: float
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class MigrationRecord:
    id: str
    tenant_id: str
    source_collection: str
    target_collection: str
    target_embedding_model: str
    status: MigrationStatus = MigrationStatus.RUNNING
    points_total: int = 0
    points_migrated: int = 0
    created_at: datetime = field(default_factory=now)
    completed_at: datetime | None = None

    @property
    def progress_ratio(self) -> float:
        if self.points_total == 0:
            return 1.0
        return min(1.0, self.points_migrated / self.points_total)
