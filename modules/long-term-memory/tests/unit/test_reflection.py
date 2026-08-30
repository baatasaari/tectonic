async def test_generate_creates_and_stores_reflection(harness):
    entry = await harness.reflection_loop.generate("t1", "agent:support-bot", "interaction-123", "The refund was issued incorrectly")
    assert entry.agent_ref == "agent:support-bot"
    assert entry.reflection_content
    assert len(harness.llm_gateway.calls) == 1


async def test_list_for_agent_returns_only_that_agents_entries(harness):
    await harness.reflection_loop.generate("t1", "agent:a", "i1", "context a")
    await harness.reflection_loop.generate("t1", "agent:b", "i2", "context b")
    entries, total = await harness.reflection_loop.list_for_agent("t1", "agent:a")
    assert len(entries) == 1
    assert total == 1
    assert entries[0].agent_ref == "agent:a"


async def test_new_reflections_default_to_not_applied(harness):
    entry = await harness.reflection_loop.generate("t1", "agent:a", "i1", "context")
    assert entry.applied is False


async def test_list_for_agent_paginates_newest_first(harness):
    first = await harness.reflection_loop.generate("t1", "agent:a", "i1", "context 1")
    second = await harness.reflection_loop.generate("t1", "agent:a", "i2", "context 2")
    third = await harness.reflection_loop.generate("t1", "agent:a", "i3", "context 3")

    page1, total1 = await harness.reflection_loop.list_for_agent("t1", "agent:a", limit=2, offset=0)
    assert total1 == 3
    assert [e.id for e in page1] == [third.id, second.id]

    page2, total2 = await harness.reflection_loop.list_for_agent("t1", "agent:a", limit=2, offset=2)
    assert total2 == 3
    assert [e.id for e in page2] == [first.id]


async def test_list_for_agent_empty_result_set(harness):
    entries, total = await harness.reflection_loop.list_for_agent("t1", "agent:nobody")
    assert entries == []
    assert total == 0
