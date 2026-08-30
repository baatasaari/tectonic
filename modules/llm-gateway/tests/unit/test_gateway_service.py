from __future__ import annotations

import pytest

from llm_gateway.core.domain import (
    AllProvidersExhaustedError,
    BudgetExceededError,
    ChatMessage,
    CompletionRequest,
    ProviderConfigRecord,
    QuotaExceededError,
    VirtualKeyInvalidError,
)
from llm_gateway.core.gateway_service import LLMGatewayService

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


async def test_quota_exceeded_rejects_before_any_provider_call(harness):
    harness.repository.seed_provider(ProviderConfigRecord(id="p1", provider_name="openai", endpoint="http://openai", priority=0))
    vk = await harness.seed_tenant()
    harness.multi_tenancy.allowed = False
    harness.multi_tenancy.reason = "requests_per_minute quota exceeded"

    with pytest.raises(QuotaExceededError):
        await harness.service.complete(_request(vk.id))

    assert harness.provider_client.calls == []


async def test_quota_check_is_called_with_the_requesting_tenant_and_resource_class(harness):
    harness.repository.seed_provider(ProviderConfigRecord(id="p1", provider_name="openai", endpoint="http://openai", priority=0))
    vk = await harness.seed_tenant(tenant_id="tenant-quota")

    await harness.service.complete(_request(vk.id, tenant_id="tenant-quota"))

    assert harness.multi_tenancy.calls == [
        {"tenant_id": "tenant-quota", "resource_class": "requests_per_minute", "amount": 1.0},
    ]


async def test_quota_check_still_runs_for_a_cache_hit(harness):
    """A cache hit is still an accepted request from the tenant's own
    quota perspective -- the pre-flight check runs before the cache
    lookup, not conditionally on a miss."""
    harness.repository.seed_provider(ProviderConfigRecord(id="p1", provider_name="openai", endpoint="http://openai", priority=0))
    vk = await harness.seed_tenant()
    await harness.service.complete(_request(vk.id))  # populates the cache
    harness.multi_tenancy.calls.clear()

    response = await harness.service.complete(_request(vk.id))  # cache hit

    assert response.cache_hit is True
    assert len(harness.multi_tenancy.calls) == 1


async def test_no_multi_tenancy_client_configured_skips_the_check(harness):
    """multi_tenancy is optional -- a service constructed without one
    (this module's own pre-existing unit tests that build
    LLMGatewayService directly) keeps working unchanged."""
    harness.repository.seed_provider(ProviderConfigRecord(id="p1", provider_name="openai", endpoint="http://openai", priority=0))
    vk = await harness.seed_tenant()
    service = LLMGatewayService(
        harness.repository, harness.cache, harness.router, harness.cost_governance, harness.failover,
        harness.settings,
    )

    response = await service.complete(_request(vk.id))

    assert response.provider_used == "openai"


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
