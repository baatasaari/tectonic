import pytest

from agentic_rag.core.domain import RetrievalOutcome

pytestmark = pytest.mark.asyncio


async def test_sufficient_on_first_hop_stops_immediately(harness):
    harness.llm_gateway.groundedness_scores = [0.9]

    result = await harness.loop.run("query", [], "tenant-a", max_hops=3, groundedness_threshold=0.85)

    assert result.outcome == RetrievalOutcome.SUFFICIENT
    assert len(result.hops) == 1
    assert harness.llm_gateway.reformulate_calls == []


async def test_insufficient_then_sufficient_reformulates_once(harness):
    harness.llm_gateway.groundedness_scores = [0.5, 0.9]

    result = await harness.loop.run("query", [], "tenant-a", max_hops=3, groundedness_threshold=0.85)

    assert result.outcome == RetrievalOutcome.SUFFICIENT
    assert len(result.hops) == 2
    assert len(harness.llm_gateway.reformulate_calls) == 1
    assert result.hops[1].query_used == harness.llm_gateway.reformulated_query


async def test_exhausts_max_hops_without_reaching_threshold(harness):
    harness.llm_gateway.groundedness_scores = [0.3, 0.4, 0.5]

    result = await harness.loop.run("query", [], "tenant-a", max_hops=3, groundedness_threshold=0.85)

    assert result.outcome == RetrievalOutcome.MAX_HOPS_REACHED
    assert len(result.hops) == 3
    assert len(harness.llm_gateway.reformulate_calls) == 2  # one fewer than hops — no reformulation after the last


async def test_best_hop_tracks_highest_score_even_if_not_final(harness):
    harness.llm_gateway.groundedness_scores = [0.7, 0.3, 0.5]  # hop 1 is the best, but not sufficient

    result = await harness.loop.run("query", [], "tenant-a", max_hops=3, groundedness_threshold=0.99)

    assert result.outcome == RetrievalOutcome.MAX_HOPS_REACHED
    assert result.best_hop.hop_number == 1
    assert result.best_hop.groundedness_score == 0.7
