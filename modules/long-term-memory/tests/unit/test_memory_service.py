from long_term_memory.core.domain import MemoryType


async def test_store_fact_item_no_downstream_call(harness):
    item = await harness.memory_service.store(
        tenant_id="t1", scope="user:alice", memory_type=MemoryType.FACT, content="Alice's favourite colour is blue",
    )
    assert item.vector_ref is None
    assert item.graph_ref is None
    assert item.status.value == "active"


async def test_store_semantic_item_indexes_in_vector_db(harness):
    item = await harness.memory_service.store(
        tenant_id="t1", scope="user:alice", memory_type=MemoryType.SEMANTIC, content="Alice prefers concise answers",
    )
    assert item.vector_ref is not None
    assert item.vector_ref in harness.vector_db.store


async def test_store_procedural_item_creates_graph_node(harness):
    item = await harness.memory_service.store(
        tenant_id="t1", scope="agent:support-bot", memory_type=MemoryType.PROCEDURAL,
        content="Always confirm order ID before issuing a refund",
    )
    assert item.graph_ref is not None
    assert item.graph_ref in harness.graph_db.nodes


async def test_query_matches_fact_by_term_overlap(harness):
    await harness.memory_service.store(
        tenant_id="t1", scope="user:alice", memory_type=MemoryType.FACT, content="Alice's favourite colour is blue",
    )
    await harness.memory_service.store(
        tenant_id="t1", scope="user:alice", memory_type=MemoryType.FACT, content="Alice lives in Berlin",
    )
    results = await harness.memory_service.query(tenant_id="t1", scope="user:alice", query="favourite colour")
    assert len(results) >= 1
    assert results[0].item.content == "Alice's favourite colour is blue"


async def test_query_includes_semantic_hits_from_vector_db(harness):
    await harness.memory_service.store(
        tenant_id="t1", scope="user:alice", memory_type=MemoryType.SEMANTIC, content="Alice enjoys hiking on weekends",
    )
    results = await harness.memory_service.query(tenant_id="t1", scope="user:alice", query="hiking")
    assert any("hiking" in r.item.content for r in results)


async def test_query_only_returns_items_in_matching_scope(harness):
    await harness.memory_service.store(tenant_id="t1", scope="user:alice", memory_type=MemoryType.FACT, content="alpha fact")
    await harness.memory_service.store(tenant_id="t1", scope="user:bob", memory_type=MemoryType.FACT, content="alpha fact")
    results = await harness.memory_service.query(tenant_id="t1", scope="user:alice", query="alpha")
    assert all(r.item.scope == "user:alice" for r in results)


async def test_query_respects_memory_types_filter(harness):
    await harness.memory_service.store(tenant_id="t1", scope="user:alice", memory_type=MemoryType.FACT, content="a fact about numbers")
    await harness.memory_service.store(tenant_id="t1", scope="user:alice", memory_type=MemoryType.SEMANTIC, content="a fact about numbers")
    results = await harness.memory_service.query(
        tenant_id="t1", scope="user:alice", query="numbers", memory_types=[MemoryType.FACT],
    )
    assert all(r.item.memory_type == MemoryType.FACT for r in results)


async def test_query_denied_for_cross_agent_scope_when_sharing_disabled(harness):
    await harness.memory_service.store(tenant_id="t1", scope="agent:a", memory_type=MemoryType.FACT, content="secret plan")
    results = await harness.memory_service.query(
        tenant_id="t1", scope="agent:a", query="secret", requesting_agent="agent:b",
    )
    assert results == []


async def test_query_allowed_for_owning_agent(harness):
    await harness.memory_service.store(tenant_id="t1", scope="agent:a", memory_type=MemoryType.FACT, content="secret plan")
    results = await harness.memory_service.query(
        tenant_id="t1", scope="agent:a", query="secret", requesting_agent="agent:a",
    )
    assert len(results) == 1


async def test_query_allowed_cross_agent_when_sharing_enabled_and_guardrails_allows(harness_factory):
    from long_term_memory.config import CrossAgentSharingConfig

    harness = harness_factory(cross_agent_config=CrossAgentSharingConfig(enabled=True, visibility_policy_ref="p1"))
    await harness.memory_service.store(tenant_id="t1", scope="agent:a", memory_type=MemoryType.FACT, content="shared plan")
    results = await harness.memory_service.query(
        tenant_id="t1", scope="agent:a", query="shared", requesting_agent="agent:b",
    )
    assert len(results) == 1
    assert harness.guardrails.calls[0]["requesting_agent"] == "agent:b"
