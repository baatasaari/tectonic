from __future__ import annotations

import pytest

from llm_gateway.core.domain import (
    AllProvidersExhaustedError,
    BudgetExceededError,
    ChatMessage,
    CompletionRequest,
    ProviderConfigRecord,
    VirtualKeyInvalidError,
)

pytestmark = pytest.mark.asyncio


def _request(vk_id: str, tenant_id: str = "tenant-a", model: str = "m1", content: str = "hello") -> CompletionRequest:
    return CompletionRequest(
        model=model, messages=[ChatMessage(role="user", content=content)], tenant_id=tenant_id, virtual_key_id=vk_id
    )


async def test_cache_miss_then_provider_call_completes_and_populates_cache(harness):
    harness.repository.seed_provider(ProviderConfigRecord(id="p1", provider_name="openai", endpoint="http://openai", priority=0))
    vk = await harness.seed_tenant()

    response = await harness.service.complete(_request(vk.id))

    assert response.cache_hit is False
    assert response.provider_used == "openai"
    assert "[openai/m1] response" in response.content
    assert len(harness.repository.request_logs) == 1

    # Second identical request should now be served from cache.
    response2 = await harness.service.complete(_request(vk.id))
    assert response2.cache_hit is True
    assert len(harness.provider_client.calls) == 1  # provider not called again


async def test_budget_exceeded_rejects_before_any_provider_call(harness):
    harness.repository.seed_provider(ProviderConfigRecord(id="p1", provider_name="openai", endpoint="http://openai", priority=0))
    vk = await harness.seed_tenant(limit_amount=0.01)

    with pytest.raises(BudgetExceededError):
        await harness.service.complete(_request(vk.id))

    assert harness.provider_client.calls == []


async def test_invalid_virtual_key_rejected(harness):
    with pytest.raises(VirtualKeyInvalidError):
        await harness.service.complete(_request("nonexistent-vk"))


async def test_failover_across_providers(harness):
    harness.repository.seed_provider(ProviderConfigRecord(id="p1", provider_name="a", endpoint="http://a", priority=0))
    harness.repository.seed_provider(ProviderConfigRecord(id="p2", provider_name="b", endpoint="http://b", priority=1))
    harness.provider_client.failing_providers.add("a")
    vk = await harness.seed_tenant()

    response = await harness.service.complete(_request(vk.id))

    assert response.provider_used == "b"


async def test_all_providers_exhausted_settles_budget_back(harness):
    harness.repository.seed_provider(ProviderConfigRecord(id="p1", provider_name="a", endpoint="http://a", priority=0))
    harness.provider_client.failing_providers.add("a")
    vk = await harness.seed_tenant()

    with pytest.raises(AllProvidersExhaustedError):
        await harness.service.complete(_request(vk.id))

    policy = await harness.repository.get_budget_policy(vk.budget_policy_ref)
    assert policy.current_spend == pytest.approx(0.0, abs=1e-9)  # reservation refunded


async def test_provider_scope_limits_candidates(harness):
    harness.repository.seed_provider(ProviderConfigRecord(id="p1", provider_name="a", endpoint="http://a", priority=0))
    harness.repository.seed_provider(ProviderConfigRecord(id="p2", provider_name="b", endpoint="http://b", priority=1))
    vk = await harness.seed_tenant(provider_scope=["b"])

    response = await harness.service.complete(_request(vk.id))

    assert response.provider_used == "b"
