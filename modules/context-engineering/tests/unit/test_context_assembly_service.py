import pytest

from context_engineering.config import BudgetConfig
from context_engineering.core.domain import CandidateItem, OntologyConfigRecord

pytestmark = pytest.mark.asyncio


async def test_all_items_fit_within_generous_budget(harness):
    items = [CandidateItem(source="rag", content="short passage one"), CandidateItem(source="stm", content="short passage two")]

    result = await harness.service.assemble(items, token_budget=1000, task_type="chat", tenant_id="tenant-a", request_ref="req-1")

    assert result.items_included_count == 2
    assert result.items_dropped_count == 0
    assert result.items_summarised_count == 0
    assert "short passage one" in result.assembled_context


async def test_overflow_item_gets_summarised_when_high_priority(harness_factory):
    harness = harness_factory()
    long_content = " ".join(["word"] * 200)
    items = [CandidateItem(source="rag", content=long_content, metadata={"role": "advisor"})]

    result = await harness.service.assemble(items, token_budget=20, task_type="chat", tenant_id="tenant-a", request_ref="req-1")

    # Too big to fit whole (200 words), but summarisation recovers it within budget.
    assert result.items_summarised_count == 1
    assert result.items_included_count == 0
    assert result.items_dropped_count == 0
    assert result.tokens_used <= 20
    assert len(harness.llm_gateway.calls) == 1


async def test_summarisation_disabled_drops_overflow_instead(harness_factory):
    harness = harness_factory(budget_config=BudgetConfig(summarisation_enabled=False))
    long_content = " ".join(["word"] * 200)
    items = [CandidateItem(source="rag", content=long_content)]

    result = await harness.service.assemble(items, token_budget=20, task_type="chat", tenant_id="tenant-a", request_ref="req-1")

    assert result.items_summarised_count == 0
    assert result.items_dropped_count == 1
    assert harness.llm_gateway.calls == []


async def test_ungoverned_policy_tag_is_excluded_before_ranking(harness):
    harness.repository.ontologies["tenant-a"] = OntologyConfigRecord(
        id="o1", tenant_id="tenant-a", version=1, policy_tags=["public"]
    )
    items = [
        CandidateItem(source="rag", content="visible content", metadata={"policy_tags": ["public"]}),
        CandidateItem(source="rag", content="hidden content", metadata={"policy_tags": ["restricted"]}),
    ]

    result = await harness.service.assemble(items, token_budget=1000, task_type="chat", tenant_id="tenant-a", request_ref="req-1")

    # The excluded item never reaches ranking/budgeting at all — it's
    # neither included nor counted as dropped, just filtered out upstream.
    assert result.items_included_count == 1
    assert result.items_dropped_count == 0
    assert "hidden content" not in result.assembled_context


async def test_assembly_is_logged(harness):
    items = [CandidateItem(source="rag", content="short passage")]
    await harness.service.assemble(items, token_budget=1000, task_type="chat", tenant_id="tenant-a", request_ref="req-1")

    assert len(harness.repository.assembly_logs) == 1
    assert harness.repository.assembly_logs[0].request_ref == "req-1"
