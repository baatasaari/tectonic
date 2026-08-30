"""Exercises the real RedisBufferStore adapter against fakeredis — this is
what catches serialization round-trip bugs the pure in-memory fake can't
(see Module 11's Graph DB temporal-filter bug for why this matters)."""
from __future__ import annotations

import fakeredis.aioredis

from short_term_memory.clients.redis_buffer_store import RedisBufferStore
from short_term_memory.core.domain import BufferState, MessageRecord


async def _store() -> RedisBufferStore:
    redis = fakeredis.aioredis.FakeRedis()
    return RedisBufferStore(redis)


async def test_missing_session_returns_none():
    store = await _store()
    assert await store.get("missing") is None


async def test_save_and_get_round_trips_messages_and_summary():
    store = await _store()
    state = BufferState(
        session_id="s1",
        messages=[
            MessageRecord(content="hello", role="user", token_count=2, salience_score=0.1),
            MessageRecord(content="Please remember this: 4521", role="user", token_count=5, salience_score=0.8),
        ],
        summary="a rolling summary",
        token_count=7,
    )
    await store.save("s1", state, ttl_seconds=60)

    fetched = await store.get("s1")
    assert fetched is not None
    assert fetched.session_id == "s1"
    assert fetched.summary == "a rolling summary"
    assert fetched.token_count == 7
    assert [m.content for m in fetched.messages] == ["hello", "Please remember this: 4521"]
    assert fetched.messages[1].salience_score == 0.8
    assert fetched.messages[0].timestamp == state.messages[0].timestamp


async def test_save_without_summary_leaves_summary_none():
    store = await _store()
    state = BufferState(session_id="s1", messages=[], summary=None, token_count=0)
    await store.save("s1", state, ttl_seconds=60)

    fetched = await store.get("s1")
    assert fetched is not None
    assert fetched.summary is None


async def test_delete_removes_all_keys():
    store = await _store()
    state = BufferState(session_id="s1", messages=[MessageRecord(content="x", role="user", token_count=1, salience_score=0.0)], summary="s", token_count=1)
    await store.save("s1", state, ttl_seconds=60)
    await store.delete("s1")
    assert await store.get("s1") is None


async def test_overwriting_a_session_replaces_prior_messages():
    store = await _store()
    first = BufferState(session_id="s1", messages=[MessageRecord(content="a", role="user", token_count=1, salience_score=0.0)], summary=None, token_count=1)
    await store.save("s1", first, ttl_seconds=60)

    second = BufferState(session_id="s1", messages=[MessageRecord(content="b", role="user", token_count=1, salience_score=0.0)], summary=None, token_count=1)
    await store.save("s1", second, ttl_seconds=60)

    fetched = await store.get("s1")
    assert [m.content for m in fetched.messages] == ["b"]
