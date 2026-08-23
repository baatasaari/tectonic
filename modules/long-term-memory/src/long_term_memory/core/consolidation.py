"""Consolidation Engine (LLD §2 sub-components): periodically merges/
deduplicates related memories and applies decay to low-relevance items
(LLD §Level 3 "State diagram: memory item lifecycle": active ->
consolidated / active -> decayed).
"""
from __future__ import annotations

from long_term_memory.core.domain import (
    ConsolidationRunRecord,
    MemoryItemRecord,
    MemoryItemStatus,
    new_id,
)
from long_term_memory.core.ports import LongTermMemoryRepository


class ConsolidationEngine:
    def __init__(self, repository: LongTermMemoryRepository, decay_threshold: float) -> None:
        self._repository = repository
        self._decay_threshold = decay_threshold

    async def run(self, tenant_id: str) -> ConsolidationRunRecord:
        merged_count = await self._merge_duplicates(tenant_id)
        decayed_count = await self._decay_low_relevance(tenant_id)

        record = ConsolidationRunRecord(
            id=new_id(), tenant_id=tenant_id, items_merged_count=merged_count, items_decayed_count=decayed_count,
        )
        return await self._repository.create_consolidation_run(record)

    async def _merge_duplicates(self, tenant_id: str) -> int:
        active_items = await self._repository.list_active(tenant_id)
        groups: dict[tuple, list[MemoryItemRecord]] = {}
        for item in active_items:
            groups.setdefault((item.scope, item.memory_type, item.content), []).append(item)

        merged_count = 0
        for group in groups.values():
            if len(group) <= 1:
                continue
            group.sort(key=lambda i: i.created_at)
            for duplicate in group[1:]:
                duplicate.status = MemoryItemStatus.CONSOLIDATED
                await self._repository.update_item(duplicate)
                merged_count += 1
        return merged_count

    async def _decay_low_relevance(self, tenant_id: str) -> int:
        decayed_count = 0
        for item in await self._repository.list_active(tenant_id):
            if item.relevance_score < self._decay_threshold:
                item.status = MemoryItemStatus.DECAYED
                await self._repository.update_item(item)
                decayed_count += 1
        return decayed_count
