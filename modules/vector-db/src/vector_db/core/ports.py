"""Abstract ports this module depends on. The Qdrant client itself is not
behind a port — a real `AsyncQdrantClient` (in embedded in-memory mode for
tests, a real cluster URL in production) is injected directly, per the
LLD's own testability contract ("in-memory Qdrant mode for fast unit
tests where available"). Only the LLM Gateway dependency and this
module's own migration bookkeeping are behind ports.
"""
from __future__ import annotations

from typing import Protocol

from vector_db.core.domain import MigrationRecord


class EmbeddingProvider(Protocol):
    async def embed(self, text: str, *, model: str | None = None) -> list[float]:
        """Requests a dense embedding for `text` from LLM Gateway, using
        `model` if given, else the module's configured default."""
        ...


class MigrationRepository(Protocol):
    async def create(self, record: MigrationRecord) -> MigrationRecord: ...

    async def get(self, migration_id: str) -> MigrationRecord | None: ...

    async def update(self, record: MigrationRecord) -> MigrationRecord: ...
