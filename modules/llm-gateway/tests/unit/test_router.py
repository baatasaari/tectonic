import pytest

from llm_gateway.config import RoutingConfig
from llm_gateway.core.domain import ProviderConfigRecord
from llm_gateway.core.fakes import FakeQualityScoreProvider
from llm_gateway.core.router import QualityAwareRouter

pytestmark = pytest.mark.asyncio


def _provider(name, priority=0, health="healthy"):
    return ProviderConfigRecord(id=name, provider_name=name, endpoint=f"http://{name}", priority=priority, health_status=health)


async def test_quality_weighted_prefers_higher_quality_score():
    providers = [_provider("openai", priority=0), _provider("anthropic", priority=0)]
    scores = FakeQualityScoreProvider(scores={("anthropic", "m1", "chat"): 0.95, ("openai", "m1", "chat"): 0.4})
    router = QualityAwareRouter(scores, RoutingConfig(strategy="quality_weighted", quality_weight=1.0, cost_weight=0.0, latency_weight=0.0))

    ranked = await router.rank_candidates(providers, model="m1", task_type="chat", allowed_provider_names=None, priority_override=[])

    assert ranked[0] == "anthropic"


async def test_cost_optimised_ignores_quality_uses_priority():
    providers = [_provider("expensive", priority=5), _provider("cheap", priority=0)]
    scores = FakeQualityScoreProvider(scores={("expensive", "m1", "chat"): 1.0, ("cheap", "m1", "chat"): 0.0})
    router = QualityAwareRouter(scores, RoutingConfig(strategy="cost_optimised"))

    ranked = await router.rank_candidates(providers, model="m1", task_type="chat", allowed_provider_names=None, priority_override=[])

    assert ranked[0] == "cheap"  # lower priority number = better, regardless of quality


async def test_down_providers_excluded():
    providers = [_provider("down_provider", health="down"), _provider("ok_provider")]
    router = QualityAwareRouter(FakeQualityScoreProvider(), RoutingConfig())

    ranked = await router.rank_candidates(providers, model="m1", task_type="chat", allowed_provider_names=None, priority_override=[])

    assert ranked == ["ok_provider"]


async def test_provider_scope_restricts_candidates():
    providers = [_provider("a"), _provider("b")]
    router = QualityAwareRouter(FakeQualityScoreProvider(), RoutingConfig())

    ranked = await router.rank_candidates(providers, model="m1", task_type="chat", allowed_provider_names=["b"], priority_override=[])

    assert ranked == ["b"]


async def test_priority_override_wins_outright():
    providers = [_provider("a", priority=0), _provider("b", priority=0)]
    scores = FakeQualityScoreProvider(scores={("a", "m1", "chat"): 1.0, ("b", "m1", "chat"): 0.0})
    router = QualityAwareRouter(scores, RoutingConfig())

    ranked = await router.rank_candidates(
        providers, model="m1", task_type="chat", allowed_provider_names=None, priority_override=["b"]
    )

    assert ranked[0] == "b"  # override beats quality score, even though "a" scores higher


async def test_no_eligible_providers_returns_empty():
    router = QualityAwareRouter(FakeQualityScoreProvider(), RoutingConfig())
    ranked = await router.rank_candidates([], model="m1", task_type="chat", allowed_provider_names=None, priority_override=[])
    assert ranked == []
