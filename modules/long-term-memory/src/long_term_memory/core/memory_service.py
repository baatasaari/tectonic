"""Mem0-based Memory Manager (LLD §2 sub-components) — deviation from
Mem0 itself; see the module README's "Design notes vs. the LLD". Core
memory CRUD, and retrieval fan-out across fact/episodic (Postgres) and
semantic (Vector DB) storage (LLD §Level 3 "Sequence: memory retrieval
spanning fact, semantic and procedural stores").

**Retrieval scoring simplification.** Fact/episodic/procedural items are
scored by query/content term overlap (this platform's usual lightweight-
fallback approach to similarity elsewhere); semantic items are scored by
Vector DB's own similarity search, which is where embedding-based
retrieval actually adds value over a keyword match.

**Consent enforcement at query time** (memory governance foundation):
`query` is where consent actually has teeth, deliberately, not at
`store` -- nothing currently calls `POST /items` from another module
(this module's own "Long-Term Memory write-back" gap is still
separately scoped), so there is no real caller today a hard
consent-at-store check would even affect; enforcing at read time
instead gives an immediate, live effect the same way
`AuthorizationService.authorize`'s own revocation check is live rather
than trusting a stale token. An item with a `purpose` set is excluded
from results unless an active `ConsentRecord` covers exactly
`(scope, purpose)` -- an item with no `purpose` at all (the default,
and every item stored before this feature existed) is never gated,
since there is nothing to check consent *for*. Consent revocation is
therefore immediate: the very next query stops returning that item,
without anything having to re-touch the item itself.
"""
from __future__ import annotations

from long_term_memory.config import CrossAgentSharingConfig
from long_term_memory.core import visibility
from long_term_memory.core.domain import (
    MemoryItemRecord,
    MemoryType,
    RankedMemoryItem,
    new_id,
    now,
)
from long_term_memory.core.ports import (
    GraphDBClient,
    GuardrailsClient,
    LongTermMemoryRepository,
    VectorDBClient,
)


def _text_match_score(query: str, content: str) -> float:
    q = query.lower().strip()
    if not q:
        return 0.0
    c = content.lower()
    if q in c:
        return 1.0
    q_words = set(q.split())
    if not q_words:
        return 0.0
    c_words = set(c.split())
    return len(q_words & c_words) / len(q_words)


class MemoryService:
    def __init__(
        self,
        repository: LongTermMemoryRepository,
        vector_db: VectorDBClient,
        graph_db: GraphDBClient,
        guardrails: GuardrailsClient,
        cross_agent_config: CrossAgentSharingConfig,
    ) -> None:
        self._repository = repository
        self._vector_db = vector_db
        self._graph_db = graph_db
        self._guardrails = guardrails
        self._cross_agent_config = cross_agent_config

    async def store(
        self, *, tenant_id: str, scope: str, memory_type: MemoryType, content: str, visibility_policy_ref: str = "",
        purpose: str = "",
    ) -> MemoryItemRecord:
        item = MemoryItemRecord(
            id=new_id(), tenant_id=tenant_id, scope=scope, memory_type=memory_type, content=content,
            visibility_policy_ref=visibility_policy_ref, purpose=purpose,
        )
        item = await self._repository.create_item(item)

        if memory_type == MemoryType.SEMANTIC:
            item.vector_ref = await self._vector_db.index(content=content, tenant_id=tenant_id, source_ref=item.id)
            item = await self._repository.update_item(item)
        elif memory_type == MemoryType.PROCEDURAL:
            item.graph_ref = await self._graph_db.create_node(name=content[:128], tenant_id=tenant_id, source_ref=item.id)
            item = await self._repository.update_item(item)

        return item

    async def query(
        self, *, tenant_id: str, scope: str, query: str, memory_types: list[MemoryType] | None = None,
        top_k: int = 10, requesting_agent: str | None = None,
    ) -> list[RankedMemoryItem]:
        allowed = await visibility.check_visibility(scope, requesting_agent, self._cross_agent_config, self._guardrails)
        if not allowed:
            return []

        active_items = [i for i in await self._repository.list_active(tenant_id, memory_types) if i.scope == scope]
        active_items = await self._filter_by_consent(tenant_id, scope, active_items)

        results: list[RankedMemoryItem] = []
        for item in active_items:
            if item.memory_type == MemoryType.SEMANTIC:
                continue
            score = _text_match_score(query, item.content)
            if score > 0:
                results.append(RankedMemoryItem(item=item, score=score))

        semantic_by_ref = {i.vector_ref: i for i in active_items if i.memory_type == MemoryType.SEMANTIC and i.vector_ref}
        if semantic_by_ref and (memory_types is None or MemoryType.SEMANTIC in memory_types):
            for hit in await self._vector_db.search(query=query, tenant_id=tenant_id, top_k=top_k):
                item = semantic_by_ref.get(hit.ref)
                if item:
                    results.append(RankedMemoryItem(item=item, score=hit.score))

        results.sort(key=lambda r: r.score, reverse=True)
        top = results[:top_k]

        for ranked in top:
            ranked.item.last_accessed_at = now()
            await self._repository.update_item(ranked.item)

        return top

    async def _filter_by_consent(
        self, tenant_id: str, scope: str, items: list[MemoryItemRecord],
    ) -> list[MemoryItemRecord]:
        purposes = {i.purpose for i in items if i.purpose}
        if not purposes:
            return items  # nothing to check consent for -- the common case today

        active_purposes = {
            purpose for purpose in purposes
            if await self._repository.get_active_consent(tenant_id, scope, purpose) is not None
        }
        return [i for i in items if not i.purpose or i.purpose in active_purposes]
