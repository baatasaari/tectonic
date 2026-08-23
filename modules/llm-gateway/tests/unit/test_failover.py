import pytest

from llm_gateway.core.domain import AllProvidersExhaustedError, ChatMessage
from llm_gateway.core.failover import FailoverManager
from llm_gateway.core.fakes import FakeProviderClient

pytestmark = pytest.mark.asyncio

_MESSAGES = [ChatMessage(role="user", content="hi")]


async def test_first_candidate_succeeds_no_failover():
    client = FakeProviderClient()
    manager = FailoverManager(client, max_attempts=3)

    outcome = await manager.call_with_failover(["a", "b"], model="m1", messages=_MESSAGES, tenant_id="t")

    assert outcome.provider_used == "a"
    assert outcome.attempts == 1


async def test_falls_over_to_second_candidate_on_failure():
    client = FakeProviderClient()
    client.failing_providers.add("a")
    manager = FailoverManager(client, max_attempts=3)

    outcome = await manager.call_with_failover(["a", "b"], model="m1", messages=_MESSAGES, tenant_id="t")

    assert outcome.provider_used == "b"
    assert outcome.attempts == 2


async def test_all_candidates_failing_raises_after_max_attempts():
    client = FakeProviderClient()
    client.failing_providers.update({"a", "b", "c"})
    manager = FailoverManager(client, max_attempts=3)

    with pytest.raises(AllProvidersExhaustedError):
        await manager.call_with_failover(["a", "b", "c"], model="m1", messages=_MESSAGES, tenant_id="t")


async def test_respects_max_attempts_even_with_more_candidates():
    client = FakeProviderClient()
    client.failing_providers.update({"a", "b"})
    manager = FailoverManager(client, max_attempts=2)

    with pytest.raises(AllProvidersExhaustedError):
        await manager.call_with_failover(["a", "b", "c"], model="m1", messages=_MESSAGES, tenant_id="t")

    assert len(client.calls) == 2  # never tried "c"


async def test_no_candidates_raises_immediately():
    client = FakeProviderClient()
    manager = FailoverManager(client, max_attempts=3)

    with pytest.raises(AllProvidersExhaustedError):
        await manager.call_with_failover([], model="m1", messages=_MESSAGES, tenant_id="t")
