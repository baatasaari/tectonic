"""Redis-backed SessionStateStore (LLD stack table: "Redis — sub-millisecond
read/write for active session state, natural TTL for session expiry")."""
from __future__ import annotations

import json
from typing import Any

from redis.asyncio import Redis

_KEY_PREFIX = "conv:session:"


class RedisSessionStateStore:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def get(self, session_id: str) -> dict[str, Any] | None:
        raw = await self._redis.get(_KEY_PREFIX + session_id)
        return json.loads(raw) if raw else None

    async def set(self, session_id: str, state: dict[str, Any], ttl_seconds: int) -> None:
        await self._redis.set(_KEY_PREFIX + session_id, json.dumps(state), ex=ttl_seconds)

    async def delete(self, session_id: str) -> None:
        await self._redis.delete(_KEY_PREFIX + session_id)
