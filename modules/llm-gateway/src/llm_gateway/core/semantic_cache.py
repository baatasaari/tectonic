"""Semantic Cache (LLD §2.2, differentiator: "semantic caching with
staleness awareness"). Checks for a cached response by exact or semantic
match; entries carry a `stale` flag a caller (or a scheduled staleness job)
can set when it detects drift in the underlying data — `invalidate_stale`
drops everything so flagged rather than everything past a fixed TTL, per
the LLD's "avoids a common production failure mode where stale cached
answers persist past their useful life."
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass, field

from llm_gateway.core.domain import ChatMessage, CompletionResult, now
from llm_gateway.core.similarity import cosine_similarity, embed, messages_text


@dataclass
class _CacheEntry:
    model: str
    text: str
    vector: Counter[str]
    result: CompletionResult
    stale: bool = False
    created_at: str = field(default_factory=lambda: now().isoformat())


class InMemorySemanticCache:
    """Used for unit tests and local dev without Redis."""

    def __init__(self, similarity_threshold: float = 0.92) -> None:
        self.similarity_threshold = similarity_threshold
        self._entries: dict[str, list[_CacheEntry]] = {}

    async def lookup(self, model: str, messages: list[ChatMessage], tenant_id: str) -> CompletionResult | None:
        text = messages_text(messages)
        vector = embed(text)
        for entry in self._entries.get(tenant_id, []):
            if entry.stale or entry.model != model:
                continue
            if entry.text == text or cosine_similarity(vector, entry.vector) >= self.similarity_threshold:
                return entry.result
        return None

    async def store(self, model: str, messages: list[ChatMessage], tenant_id: str, result: CompletionResult) -> None:
        text = messages_text(messages)
        self._entries.setdefault(tenant_id, []).append(
            _CacheEntry(model=model, text=text, vector=embed(text), result=result)
        )

    def flag_stale(self, tenant_id: str) -> None:
        """Called by the (external, not built here) drift-detection signal
        to mark every current entry for a tenant stale."""
        for entry in self._entries.get(tenant_id, []):
            entry.stale = True

    async def invalidate_stale(self, tenant_id: str) -> int:
        before = len(self._entries.get(tenant_id, []))
        self._entries[tenant_id] = [e for e in self._entries.get(tenant_id, []) if not e.stale]
        return before - len(self._entries[tenant_id])


class RedisSemanticCache:
    """Brute-force scan over a per-tenant Redis list — an MVP stand-in for
    RedisVL's ANN index. Fine at the entry counts a single-tenant cache
    realistically holds; swap for a real vector index before that stops
    being true."""

    def __init__(self, redis, similarity_threshold: float = 0.92, max_entries_per_tenant: int = 500) -> None:
        self._redis = redis
        self.similarity_threshold = similarity_threshold
        self.max_entries_per_tenant = max_entries_per_tenant

    def _key(self, tenant_id: str) -> str:
        return f"llm_gateway:semantic_cache:{tenant_id}"

    async def lookup(self, model: str, messages: list[ChatMessage], tenant_id: str) -> CompletionResult | None:
        text = messages_text(messages)
        vector = embed(text)
        raw_entries = await self._redis.lrange(self._key(tenant_id), 0, -1)
        for raw in raw_entries:
            data = json.loads(raw)
            if data["stale"] or data["model"] != model:
                continue
            if data["text"] == text or cosine_similarity(vector, Counter(data["vector"])) >= self.similarity_threshold:
                r = data["result"]
                return CompletionResult(
                    content=r["content"],
                    input_tokens=r["input_tokens"],
                    output_tokens=r["output_tokens"],
                    cost=r["cost"],
                    model_used=r["model_used"],
                )
        return None

    async def store(self, model: str, messages: list[ChatMessage], tenant_id: str, result: CompletionResult) -> None:
        text = messages_text(messages)
        entry = {
            "model": model,
            "text": text,
            "vector": dict(embed(text)),
            "result": asdict(result),
            "stale": False,
            "created_at": now().isoformat(),
        }
        key = self._key(tenant_id)
        await self._redis.lpush(key, json.dumps(entry))
        await self._redis.ltrim(key, 0, self.max_entries_per_tenant - 1)

    async def invalidate_stale(self, tenant_id: str) -> int:
        key = self._key(tenant_id)
        raw_entries = await self._redis.lrange(key, 0, -1)
        fresh = [raw for raw in raw_entries if not json.loads(raw)["stale"]]
        removed = len(raw_entries) - len(fresh)
        if removed:
            await self._redis.delete(key)
            if fresh:
                await self._redis.rpush(key, *fresh)
        return removed
