"""In-memory fakes for the ports in core/ports.py — the unit-test tier
for this module's non-Qdrant dependencies. Qdrant itself is exercised for
real, in embedded in-memory mode (see core/ports.py's module docstring).
"""
from __future__ import annotations

import copy
import hashlib

from vector_db.core.domain import MigrationRecord


class StubEmbeddingProvider:
    """Deterministic canned embeddings: hashes the text into a fixed-size
    float vector, so the same text always maps to the same vector (needed
    for the migration-manager's re-embedding tests to be meaningful) while
    remaining a pure local function with zero network dependency."""

    def __init__(self, dimension: int = 8) -> None:
        self.dimension = dimension
        self.calls: list[dict] = []

    async def embed(self, text: str, *, model: str | None = None) -> list[float]:
        self.calls.append({"text": text, "model": model})
        seed = f"{model or 'default'}:{text}".encode()
        digest = hashlib.sha256(seed).digest()
        return [(digest[i % len(digest)] / 255.0) * 2 - 1 for i in range(self.dimension)]


class InMemoryMigrationRepository:
    def __init__(self) -> None:
        self.migrations: dict[str, MigrationRecord] = {}

    async def create(self, record: MigrationRecord) -> MigrationRecord:
        self.migrations[record.id] = copy.deepcopy(record)
        return copy.deepcopy(record)

    async def get(self, migration_id: str) -> MigrationRecord | None:
        rec = self.migrations.get(migration_id)
        return copy.deepcopy(rec) if rec else None

    async def update(self, record: MigrationRecord) -> MigrationRecord:
        self.migrations[record.id] = copy.deepcopy(record)
        return copy.deepcopy(record)
