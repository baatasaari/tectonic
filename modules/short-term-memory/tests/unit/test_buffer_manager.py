from short_term_memory.config import BufferConfig, SalienceConfig


async def test_append_within_budget_no_overflow(harness):
    result = await harness.manager.append("s1", "t1", "hello there", "user")
    assert result.overflow_triggered is False
    assert result.state.token_count > 0
    assert len(result.state.messages) == 1


async def test_append_accumulates_across_calls(harness):
    await harness.manager.append("s1", "t1", "first message", "user")
    result = await harness.manager.append("s1", "t1", "second message", "assistant")
    assert len(result.state.messages) == 2


async def test_overflow_triggers_summarisation_and_retains_high_salience(harness_factory):
    harness = harness_factory(
        buffer_config=BufferConfig(default_token_budget=15, session_ttl_seconds=1800),
        salience_config=SalienceConfig(retention_priority_threshold=0.7),
    )
    await harness.manager.append("s1", "t1", "Please remember this: account number 4521", "user")
    result = await harness.manager.append("s1", "t1", "just some ordinary filler chatter about the weather today", "user")

    assert result.overflow_triggered is True
    assert result.state.summary is not None
    contents = [m.content for m in result.state.messages]
    assert "Please remember this: account number 4521" in contents
    assert "just some ordinary filler chatter about the weather today" not in contents
    assert len(harness.llm_gateway.calls) == 1


async def test_overflow_with_no_low_salience_items_leaves_state_unchanged(harness_factory):
    harness = harness_factory(
        buffer_config=BufferConfig(default_token_budget=5, session_ttl_seconds=1800),
        salience_config=SalienceConfig(retention_priority_threshold=0.7),
    )
    result = await harness.manager.append("s1", "t1", "Please remember this: the number is 42", "user")
    assert result.overflow_triggered is True
    assert result.state.summary is None
    assert len(harness.llm_gateway.calls) == 0


async def test_get_missing_session_returns_none(harness):
    assert await harness.manager.get("does-not-exist") is None


async def test_get_after_append_returns_state(harness):
    await harness.manager.append("s1", "t1", "hello", "user")
    state = await harness.manager.get("s1")
    assert state is not None
    assert state.session_id == "s1"


async def test_delete_returns_true_when_existed(harness):
    await harness.manager.append("s1", "t1", "hello", "user")
    assert await harness.manager.delete("s1") is True
    assert await harness.manager.get("s1") is None


async def test_delete_returns_false_when_never_existed(harness):
    assert await harness.manager.delete("never-existed") is False
