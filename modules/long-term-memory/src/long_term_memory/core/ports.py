"""Abstract ports this module depends on: its own Postgres-backed
repository, plus every delegated/external module dependency named in the
LLD's component diagram (Vector DB, Graph DB, LLM Gateway, Guardrails).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from long_term_memory.core.domain import (
    ConsentRecord,
    ConsolidationRunRecord,
    DeletionRecord,
    LegalHoldRecord,
    MemoryItemRecord,
    MemoryType,
    ReflectionEntryRecord,
)


class LongTermMemoryRepository(Protocol):
    async def create_item(self, record: MemoryItemRecord) -> MemoryItemRecord: ...

    async def get_item(self, tenant_id: str, item_id: str) -> MemoryItemRecord | None: ...

    async def update_item(self, record: MemoryItemRecord) -> MemoryItemRecord: ...

    async def list_by_scope(self, tenant_id: str, scope: str) -> list[MemoryItemRecord]: ...

    async def list_active(self, tenant_id: str, memory_types: list[MemoryType] | None = None) -> list[MemoryItemRecord]: ...

    async def delete_items(self, tenant_id: str, item_ids: list[str]) -> None: ...

    async def create_consolidation_run(self, record: ConsolidationRunRecord) -> ConsolidationRunRecord: ...

    async def create_reflection(self, record: ReflectionEntryRecord) -> ReflectionEntryRecord: ...

    async def list_reflections(
        self, tenant_id: str, agent_ref: str, limit: int = 50, offset: int = 0
    ) -> tuple[list[ReflectionEntryRecord], int]: ...

    async def create_deletion_record(self, record: DeletionRecord) -> DeletionRecord: ...

    async def get_deletion_record(self, tenant_id: str, deletion_id: str) -> DeletionRecord | None: ...

    # -- Memory governance: consent records and legal holds --

    async def create_consent_record(self, record: ConsentRecord) -> ConsentRecord: ...

    async def get_active_consent(self, tenant_id: str, scope: str, purpose: str) -> ConsentRecord | None:
        """The most recent not-yet-revoked consent for this (scope, purpose),
        if any -- what MemoryService.query and ConsentService.revoke both
        need."""
        ...

    async def revoke_consent(self, tenant_id: str, consent_id: str) -> ConsentRecord | None: ...

    async def list_consents(self, tenant_id: str, scope: str) -> list[ConsentRecord]: ...

    async def create_legal_hold(self, record: LegalHoldRecord) -> LegalHoldRecord: ...

    async def get_active_legal_hold(self, tenant_id: str, scope: str) -> LegalHoldRecord | None:
        """The most recent not-yet-released hold on this scope, if any --
        what ForgettingEngine.execute checks before deleting anything."""
        ...

    async def release_legal_hold(self, tenant_id: str, hold_id: str) -> LegalHoldRecord | None: ...

    async def list_legal_holds(self, tenant_id: str, scope: str) -> list[LegalHoldRecord]: ...


@dataclass
class VectorHit:
    ref: str
    content: str
    score: float


class VectorDBClient(Protocol):
    async def index(self, *, content: str, tenant_id: str, source_ref: str) -> str: ...

    async def search(self, *, query: str, tenant_id: str, top_k: int) -> list[VectorHit]: ...

    async def delete(self, point_id: str, tenant_id: str) -> None: ...


@dataclass
class GraphHit:
    ref: str
    name: str


class GraphDBClient(Protocol):
    async def create_node(self, *, name: str, tenant_id: str, source_ref: str) -> str: ...

    async def query_related(self, *, node_id: str, tenant_id: str) -> list[GraphHit]: ...

    async def delete_by_source_ref(self, *, tenant_id: str, source_ref: str) -> None: ...


class LLMGatewayClient(Protocol):
    async def reflect(self, context: str, tenant_id: str) -> str: ...


class GuardrailsClient(Protocol):
    async def check_visibility(self, *, scope: str, requesting_agent: str, policy_ref: str) -> bool: ...
