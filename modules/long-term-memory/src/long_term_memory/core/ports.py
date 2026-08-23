"""Abstract ports this module depends on: its own Postgres-backed
repository, plus every delegated/external module dependency named in the
LLD's component diagram (Vector DB, Graph DB, LLM Gateway, Guardrails).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from long_term_memory.core.domain import (
    ConsolidationRunRecord,
    DeletionRecord,
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

    async def list_reflections(self, tenant_id: str, agent_ref: str) -> list[ReflectionEntryRecord]: ...

    async def create_deletion_record(self, record: DeletionRecord) -> DeletionRecord: ...

    async def get_deletion_record(self, tenant_id: str, deletion_id: str) -> DeletionRecord | None: ...


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
