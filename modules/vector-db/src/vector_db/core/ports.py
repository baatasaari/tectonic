"""Abstract ports this module depends on. The Qdrant client itself is not
behind a port — a real `AsyncQdrantClient` (in embedded in-memory mode for
tests, a real cluster URL in production) is injected directly, per the
LLD's own testability contract ("in-memory Qdrant mode for fast unit
tests where available"). The LLM Gateway dependency, this module's own
migration bookkeeping, and the Multi-tenancy quota pre-flight check are
behind ports.
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


class MultiTenancyQuotaClient(Protocol):
    """Real-time pre-flight check against Multi-tenancy's own
    `POST /tenants/{id}/quota/check` (independent architecture
    assessment §5.2 / §3.4 point 5) before this module writes a new
    point -- `vector_count` is a capacity-shaped resource class in
    `QuotaEnforcementService`'s own terms: Multi-tenancy doesn't track
    live usage for it, so this module (the real source of truth for how
    many vectors a tenant currently has indexed) supplies
    `current_usage` itself. See `LLMGatewayService`'s own
    `MultiTenancyQuotaClient` (Module 3) for the rate-shaped
    counterpart, which needs no `current_usage`."""

    async def check_quota(
        self, *, tenant_id: str, resource_class: str, amount: float = 1.0, current_usage: float | None = None,
    ) -> tuple[bool, str]: ...
