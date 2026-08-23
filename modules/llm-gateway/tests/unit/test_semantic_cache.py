import pytest

from llm_gateway.core.domain import ChatMessage, CompletionResult
from llm_gateway.core.semantic_cache import InMemorySemanticCache

pytestmark = pytest.mark.asyncio


def _result(content="cached answer") -> CompletionResult:
    return CompletionResult(content=content, input_tokens=5, output_tokens=5, cost=0.001, model_used="m1")


async def test_miss_on_empty_cache():
    cache = InMemorySemanticCache()
    hit = await cache.lookup("m1", [ChatMessage(role="user", content="hello")], "tenant-a")
    assert hit is None


async def test_exact_match_hit():
    cache = InMemorySemanticCache()
    messages = [ChatMessage(role="user", content="what is the capital of France")]
    await cache.store("m1", messages, "tenant-a", _result())

    hit = await cache.lookup("m1", messages, "tenant-a")
    assert hit is not None
    assert hit.content == "cached answer"


async def test_near_duplicate_prompt_hits_above_threshold():
    cache = InMemorySemanticCache(similarity_threshold=0.8)
    await cache.store("m1", [ChatMessage(role="user", content="what is the capital city of France")], "tenant-a", _result())

    hit = await cache.lookup("m1", [ChatMessage(role="user", content="what is the capital city of france")], "tenant-a")
    assert hit is not None  # same tokens modulo case -> identical term-frequency vector


async def test_unrelated_prompt_misses():
    cache = InMemorySemanticCache(similarity_threshold=0.8)
    await cache.store("m1", [ChatMessage(role="user", content="what is the capital of France")], "tenant-a", _result())

    hit = await cache.lookup("m1", [ChatMessage(role="user", content="write me a poem about the ocean")], "tenant-a")
    assert hit is None


async def test_different_model_does_not_match():
    cache = InMemorySemanticCache()
    messages = [ChatMessage(role="user", content="hello there")]
    await cache.store("m1", messages, "tenant-a", _result())

    hit = await cache.lookup("m2", messages, "tenant-a")
    assert hit is None


async def test_tenant_isolation():
    cache = InMemorySemanticCache()
    messages = [ChatMessage(role="user", content="hello there")]
    await cache.store("m1", messages, "tenant-a", _result())

    hit = await cache.lookup("m1", messages, "tenant-b")
    assert hit is None


async def test_flag_stale_then_invalidate_removes_entries():
    cache = InMemorySemanticCache()
    messages = [ChatMessage(role="user", content="hello there")]
    await cache.store("m1", messages, "tenant-a", _result())

    cache.flag_stale("tenant-a")
    assert await cache.lookup("m1", messages, "tenant-a") is None  # stale entries never match

    removed = await cache.invalidate_stale("tenant-a")
    assert removed == 1
