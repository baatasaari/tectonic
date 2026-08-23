import pytest

from agentic_rag.core.domain import RetrievalOutcome

pytestmark = pytest.mark.asyncio


async def test_retrieve_persists_request_hops_and_result(harness):
    harness.llm_gateway.groundedness_scores = [0.9]

    result = await harness.service.retrieve(
        query="what is the mortgage rate", scope=["mortgages"], tenant_id="tenant-a",
        max_hops=3, groundedness_threshold=0.85,
    )

    assert result.outcome == RetrievalOutcome.SUFFICIENT
    assert result.total_hops == 1
    assert "mortgage rate" in result.final_context
    assert len(result.provenance_chain) > 0

    [request] = harness.repository.requests.values()
    assert len(harness.repository.hops[request.id]) == 1
    assert harness.repository.results[request.id].outcome == RetrievalOutcome.SUFFICIENT


async def test_retrieve_multi_hop_persists_all_hops(harness):
    harness.llm_gateway.groundedness_scores = [0.4, 0.9]

    result = await harness.service.retrieve(
        query="q", scope=[], tenant_id="tenant-a", max_hops=3, groundedness_threshold=0.85
    )

    assert result.total_hops == 2
    [request] = harness.repository.requests.values()
    assert len(harness.repository.hops[request.id]) == 2
