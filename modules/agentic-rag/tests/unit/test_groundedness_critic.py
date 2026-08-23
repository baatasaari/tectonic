import pytest

from agentic_rag.core.domain import Provenance, RetrievalSource, RetrievedItem
from agentic_rag.core.fakes import StubLLMGatewayClient
from agentic_rag.core.groundedness_critic import HeuristicGroundednessCritic, LLMGroundednessCritic

pytestmark = pytest.mark.asyncio


def _item(content: str) -> RetrievedItem:
    return RetrievedItem(content=content, source=RetrievalSource.VECTOR_DB, provenance=Provenance(source_document="d1"))


async def test_heuristic_critic_no_items_scores_zero_with_gap_message():
    result = await HeuristicGroundednessCritic().assess("what is the mortgage rate", [], "tenant-a")
    assert result.score == 0.0
    assert "no context" in result.gaps


async def test_heuristic_critic_high_overlap_scores_high():
    items = [_item("the current mortgage rate is 6.5 percent")]
    result = await HeuristicGroundednessCritic().assess("what is the mortgage rate", items, "tenant-a")
    assert result.score > 0.5
    assert result.gaps == ""


async def test_heuristic_critic_low_overlap_scores_low_with_gap_message():
    items = [_item("our office hours are nine to five")]
    result = await HeuristicGroundednessCritic().assess("what is the mortgage rate", items, "tenant-a")
    assert result.score < 0.5
    assert result.gaps != ""


async def test_llm_critic_delegates_to_gateway():
    llm_gateway = StubLLMGatewayClient()
    llm_gateway.groundedness_scores = [0.42]
    critic = LLMGroundednessCritic(llm_gateway)

    result = await critic.assess("query", [_item("content")], "tenant-a")

    assert result.score == 0.42
    assert len(llm_gateway.assess_calls) == 1
