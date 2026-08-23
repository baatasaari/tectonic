"""In-memory fakes for the ports in core/ports.py — the unit-test tier,
mirroring the other modules' core/fakes.py.
"""
from __future__ import annotations

import copy

from long_term_memory.core.domain import (
    ConsolidationRunRecord,
    DeletionRecord,
    MemoryItemRecord,
    MemoryType,
    ReflectionEntryRecord,
)
from long_term_memory.core.ports import GraphHit, VectorHit


class InMemoryLongTermMemoryRepository:
    def __init__(self) -> None:
        self.items: dict[str, MemoryItemRecord] = {}
        self.consolidation_runs: list[ConsolidationRunRecord] = []
        self.reflections: list[ReflectionEntryRecord] = []
        self.deletion_records: dict[str, DeletionRecord] = {}

    async def create_item(self, record: MemoryItemRecord) -> MemoryItemRecord:
        self.items[record.id] = copy.deepcopy(record)
        return copy.deepcopy(record)

    async def get_item(self, tenant_id: str, item_id: str) -> MemoryItemRecord | None:
        rec = self.items.get(item_id)
        if rec is None or rec.tenant_id != tenant_id:
            return None
        return copy.deepcopy(rec)

    async def update_item(self, record: MemoryItemRecord) -> MemoryItemRecord:
        self.items[record.id] = copy.deepcopy(record)
        return copy.deepcopy(record)

    async def list_by_scope(self, tenant_id: str, scope: str) -> list[MemoryItemRecord]:
        return [copy.deepcopy(i) for i in self.items.values() if i.tenant_id == tenant_id and i.scope == scope]

    async def list_active(self, tenant_id: str, memory_types: list[MemoryType] | None = None) -> list[MemoryItemRecord]:
        from long_term_memory.core.domain import MemoryItemStatus

        result = [
            copy.deepcopy(i) for i in self.items.values()
            if i.tenant_id == tenant_id and i.status == MemoryItemStatus.ACTIVE
            and (memory_types is None or i.memory_type in memory_types)
        ]
        return result

    async def delete_items(self, tenant_id: str, item_ids: list[str]) -> None:
        for item_id in item_ids:
            item = self.items.get(item_id)
            if item and item.tenant_id == tenant_id:
                del self.items[item_id]

    async def create_consolidation_run(self, record: ConsolidationRunRecord) -> ConsolidationRunRecord:
        self.consolidation_runs.append(copy.deepcopy(record))
        return copy.deepcopy(record)

    async def create_reflection(self, record: ReflectionEntryRecord) -> ReflectionEntryRecord:
        self.reflections.append(copy.deepcopy(record))
        return copy.deepcopy(record)

    async def list_reflections(self, tenant_id: str, agent_ref: str) -> list[ReflectionEntryRecord]:
        return [
            copy.deepcopy(r) for r in self.reflections if r.tenant_id == tenant_id and r.agent_ref == agent_ref
        ]

    async def create_deletion_record(self, record: DeletionRecord) -> DeletionRecord:
        self.deletion_records[record.id] = copy.deepcopy(record)
        return copy.deepcopy(record)

    async def get_deletion_record(self, tenant_id: str, deletion_id: str) -> DeletionRecord | None:
        rec = self.deletion_records.get(deletion_id)
        if rec is None or rec.tenant_id != tenant_id:
            return None
        return copy.deepcopy(rec)


class StubVectorDBClient:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}  # point_id -> content
        self.deleted: list[str] = []
        self.canned_hits: list[VectorHit] | None = None

    async def index(self, *, content: str, tenant_id: str, source_ref: str) -> str:
        point_id = f"vec-{len(self.store) + 1}"
        self.store[point_id] = content
        return point_id

    async def search(self, *, query: str, tenant_id: str, top_k: int) -> list[VectorHit]:
        if self.canned_hits is not None:
            return self.canned_hits[:top_k]
        query_lower = query.lower()
        hits = [
            VectorHit(ref=ref, content=content, score=1.0 if query_lower in content.lower() else 0.2)
            for ref, content in self.store.items()
        ]
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:top_k]

    async def delete(self, point_id: str, tenant_id: str) -> None:
        self.store.pop(point_id, None)
        self.deleted.append(point_id)


class StubGraphDBClient:
    def __init__(self) -> None:
        self.nodes: dict[str, str] = {}  # node_id -> name
        self.deleted_source_refs: list[str] = []

    async def create_node(self, *, name: str, tenant_id: str, source_ref: str) -> str:
        node_id = f"node-{len(self.nodes) + 1}"
        self.nodes[node_id] = name
        return node_id

    async def query_related(self, *, node_id: str, tenant_id: str) -> list[GraphHit]:
        return [GraphHit(ref=node_id, name=self.nodes.get(node_id, ""))]

    async def delete_by_source_ref(self, *, tenant_id: str, source_ref: str) -> None:
        self.deleted_source_refs.append(source_ref)


class StubLLMGatewayClient:
    def __init__(self) -> None:
        self.canned_reflection: str | None = None
        self.calls: list[dict] = []

    async def reflect(self, context: str, tenant_id: str) -> str:
        self.calls.append({"context": context, "tenant_id": tenant_id})
        return self.canned_reflection or f"Reflection on: {context[:60]}"


class StubGuardrailsClient:
    def __init__(self) -> None:
        self.allow: bool = True
        self.calls: list[dict] = []

    async def check_visibility(self, *, scope: str, requesting_agent: str, policy_ref: str) -> bool:
        self.calls.append({"scope": scope, "requesting_agent": requesting_agent, "policy_ref": policy_ref})
        return self.allow
