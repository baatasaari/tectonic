"""Forgetting Engine (LLD §2 sub-components, §Level 3 "Sequence:
verifiable right-to-erasure"): executes verifiable deletion across all
storage backends on erasure request, with a cryptographic deletion proof
so forgetting is auditable rather than "trust us it's gone."
"""
from __future__ import annotations

import hashlib
import json

from long_term_memory.core.domain import DeletionRecord, MemoryItemRecord, new_id, now
from long_term_memory.core.ports import GraphDBClient, LongTermMemoryRepository, VectorDBClient


def compute_deletion_proof(items: list[MemoryItemRecord]) -> str:
    payload = json.dumps(
        sorted(
            [{"id": i.id, "content_hash": hashlib.sha256(i.content.encode()).hexdigest()} for i in items],
            key=lambda x: x["id"],
        )
    )
    return hashlib.sha256(payload.encode()).hexdigest()


class ForgettingEngine:
    def __init__(self, repository: LongTermMemoryRepository, vector_db: VectorDBClient, graph_db: GraphDBClient) -> None:
        self._repository = repository
        self._vector_db = vector_db
        self._graph_db = graph_db

    async def execute(self, tenant_id: str, subject_ref: str, requested_by: str) -> DeletionRecord:
        items = await self._repository.list_by_scope(tenant_id, subject_ref)
        proof_hash = compute_deletion_proof(items)
        item_ids = [i.id for i in items]

        for item in items:
            if item.vector_ref:
                await self._vector_db.delete(item.vector_ref, tenant_id)
        await self._graph_db.delete_by_source_ref(tenant_id=tenant_id, source_ref=subject_ref)
        await self._repository.delete_items(tenant_id, item_ids)

        record = DeletionRecord(
            id=new_id(), tenant_id=tenant_id, subject_ref=subject_ref, memory_items_deleted=item_ids,
            deletion_proof_hash=proof_hash, requested_by=requested_by, completed_at=now(),
        )
        return await self._repository.create_deletion_record(record)
