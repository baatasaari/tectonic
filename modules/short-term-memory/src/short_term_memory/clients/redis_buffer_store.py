"""Redis-backed BufferStore (LLD §3 "Data model (Redis structures, not
relational)") — implements the LLD's three key patterns literally:
`stm:session:{id}:messages` (List), `stm:session:{id}:summary` (String),
`stm:session:{id}:token_count` (Integer), all sharing one TTL.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime

from redis.asyncio import Redis

from short_term_memory.core.domain import BufferState, MessageRecord

_PREFIX = "stm:session:"


def _messages_key(session_id: str) -> str:
    return f"{_PREFIX}{session_id}:messages"


def _summary_key(session_id: str) -> str:
    return f"{_PREFIX}{session_id}:summary"


def _token_count_key(session_id: str) -> str:
    return f"{_PREFIX}{session_id}:token_count"


def _decode(value: bytes | str | None) -> str | None:
    # The redis-py client this module constructs doesn't set
    # decode_responses, so string replies come back as bytes; decode
    # defensively here rather than depending on caller configuration.
    if value is None:
        return None
    return value.decode("utf-8") if isinstance(value, bytes) else value


class RedisBufferStore:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def get(self, session_id: str) -> BufferState | None:
        exists = await self._redis.exists(_messages_key(session_id), _summary_key(session_id), _token_count_key(session_id))
        if not exists:
            return None

        raw_messages = await self._redis.lrange(_messages_key(session_id), 0, -1)
        messages = [_message_from_json(json.loads(_decode(m))) for m in raw_messages]
        summary = _decode(await self._redis.get(_summary_key(session_id)))
        raw_token_count = _decode(await self._redis.get(_token_count_key(session_id)))
        token_count = int(raw_token_count) if raw_token_count is not None else 0

        return BufferState(session_id=session_id, messages=messages, summary=summary, token_count=token_count)

    async def save(self, session_id: str, state: BufferState, ttl_seconds: int) -> None:
        pipe = self._redis.pipeline()
        pipe.delete(_messages_key(session_id), _summary_key(session_id), _token_count_key(session_id))
        if state.messages:
            serialized = [json.dumps(_message_to_json(m)) for m in state.messages]
            pipe.rpush(_messages_key(session_id), *serialized)
        if state.summary is not None:
            pipe.set(_summary_key(session_id), state.summary)
        pipe.set(_token_count_key(session_id), state.token_count)
        pipe.expire(_messages_key(session_id), ttl_seconds)
        pipe.expire(_token_count_key(session_id), ttl_seconds)
        if state.summary is not None:
            pipe.expire(_summary_key(session_id), ttl_seconds)
        await pipe.execute()

    async def delete(self, session_id: str) -> None:
        await self._redis.delete(_messages_key(session_id), _summary_key(session_id), _token_count_key(session_id))


def _message_to_json(message: MessageRecord) -> dict:
    data = asdict(message)
    data["timestamp"] = message.timestamp.isoformat()
    return data


def _message_from_json(data: dict) -> MessageRecord:
    data = dict(data)
    data["timestamp"] = datetime.fromisoformat(data["timestamp"])
    return MessageRecord(**data)
