"""Redis-backed QualityScoreProvider (LLD stack table: "Quality score feed
— consumed from Evaluation Framework via event bus, stored in Redis for
fast routing-time lookup ... Postgres would be too slow for the hot path").

This module doesn't consume the event bus itself (Evaluation Framework
isn't built yet) — it's the Redis read side, plus a `record_score` write
path a consumer of that event bus would call. Falls back to a neutral 0.5
for anything not yet scored, same "unknown is neutral, not zero" principle
as leaving a step unrouted rather than penalizing it.
"""
from __future__ import annotations

from redis.asyncio import Redis

_KEY_PREFIX = "llm_gateway:quality_score:"


def _key(provider: str, model: str, task_type: str) -> str:
    return f"{_KEY_PREFIX}{provider}:{model}:{task_type}"


class RedisQualityScoreProvider:
    def __init__(self, redis: Redis, default: float = 0.5) -> None:
        self._redis = redis
        self.default = default

    async def get_score(self, provider: str, model: str, task_type: str) -> float:
        raw = await self._redis.get(_key(provider, model, task_type))
        return float(raw) if raw is not None else self.default

    async def record_score(self, provider: str, model: str, task_type: str, score: float) -> None:
        await self._redis.set(_key(provider, model, task_type), str(max(0.0, min(1.0, score))))
