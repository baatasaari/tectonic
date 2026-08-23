"""Redis-backed CircuitBreakerStore (LLD stack table: "Circuit breaker
state — Redis, fast read/write for per-tool circuit state, natural TTL for
half-open retry windows")."""
from __future__ import annotations

import json
from datetime import datetime

from redis.asyncio import Redis

from tool_orchestration.core.domain import CircuitBreakerStateRecord, CircuitState

_KEY_PREFIX = "tool_orchestration:circuit:"


def _serialize(record: CircuitBreakerStateRecord) -> str:
    return json.dumps(
        {
            "state": record.state.value,
            "opened_at": record.opened_at.isoformat() if record.opened_at else None,
            "next_retry_at": record.next_retry_at.isoformat() if record.next_retry_at else None,
        }
    )


def _deserialize(tool_id: str, raw: str) -> CircuitBreakerStateRecord:
    data = json.loads(raw)
    return CircuitBreakerStateRecord(
        tool_id=tool_id,
        state=CircuitState(data["state"]),
        opened_at=datetime.fromisoformat(data["opened_at"]) if data["opened_at"] else None,
        next_retry_at=datetime.fromisoformat(data["next_retry_at"]) if data["next_retry_at"] else None,
    )


class RedisCircuitBreakerStore:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def get_state(self, tool_id: str) -> CircuitBreakerStateRecord:
        raw = await self._redis.get(_KEY_PREFIX + tool_id)
        if raw is None:
            return CircuitBreakerStateRecord(tool_id=tool_id, state=CircuitState.CLOSED)
        return _deserialize(tool_id, raw)

    async def set_state(self, record: CircuitBreakerStateRecord) -> None:
        await self._redis.set(_KEY_PREFIX + record.tool_id, _serialize(record))
