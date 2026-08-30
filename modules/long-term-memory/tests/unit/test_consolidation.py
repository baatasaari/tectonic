from long_term_memory.core.domain import MemoryItemStatus, MemoryType


async def test_merges_exact_duplicate_items(harness):
    await harness.memory_service.store(tenant_id="t1", scope="user:alice", memory_type=MemoryType.FACT, content="duplicate content")
    await harness.memory_service.store(tenant_id="t1", scope="user:alice", memory_type=MemoryType.FACT, content="duplicate content")
    await harness.memory_service.store(tenant_id="t1", scope="user:alice", memory_type=MemoryType.FACT, content="unique content")

    run = await harness.consolidation_engine.run("t1")
    assert run.items_merged_count == 1

    active = await harness.repository.list_active("t1")
    assert len(active) == 2  # one canonical duplicate + the unique item


async def test_no_duplicates_merges_nothing(harness):
    await harness.memory_service.store(tenant_id="t1", scope="user:alice", memory_type=MemoryType.FACT, content="a")
    await harness.memory_service.store(tenant_id="t1", scope="user:alice", memory_type=MemoryType.FACT, content="b")
    run = await harness.consolidation_engine.run("t1")
    assert run.items_merged_count == 0


async def test_decays_items_below_threshold(harness_factory):
    from long_term_memory.config import ConsolidationConfig

    harness = harness_factory(consolidation_config=ConsolidationConfig(decay_threshold=0.5))
    item = await harness.memory_service.store(tenant_id="t1", scope="user:alice", memory_type=MemoryType.FACT, content="stale fact")
    item.relevance_score = 0.1
    await harness.repository.update_item(item)

    run = await harness.consolidation_engine.run("t1")
    assert run.items_decayed_count == 1

    updated = await harness.repository.get_item("t1", item.id)
    assert updated.status == MemoryItemStatus.DECAYED


async def test_duplicates_scoped_by_scope_and_memory_type(harness):
    await harness.memory_service.store(tenant_id="t1", scope="user:alice", memory_type=MemoryType.FACT, content="same text")
    await harness.memory_service.store(tenant_id="t1", scope="user:bob", memory_type=MemoryType.FACT, content="same text")
    run = await harness.consolidation_engine.run("t1")
    assert run.items_merged_count == 0
