from long_term_memory.core.domain import MemoryType
from long_term_memory.core.forgetting import compute_deletion_proof


async def test_erasure_deletes_all_items_for_subject(harness):
    await harness.memory_service.store(tenant_id="t1", scope="user:alice", memory_type=MemoryType.FACT, content="fact one")
    await harness.memory_service.store(tenant_id="t1", scope="user:alice", memory_type=MemoryType.SEMANTIC, content="semantic one")
    await harness.memory_service.store(tenant_id="t1", scope="user:bob", memory_type=MemoryType.FACT, content="unrelated")

    record = await harness.forgetting_engine.execute("t1", "user:alice", "compliance-officer")

    assert len(record.memory_items_deleted) == 2
    assert record.deletion_proof_hash

    remaining = await harness.repository.list_by_scope("t1", "user:alice")
    assert remaining == []
    other_scope = await harness.repository.list_by_scope("t1", "user:bob")
    assert len(other_scope) == 1


async def test_erasure_deletes_vector_db_points(harness):
    item = await harness.memory_service.store(
        tenant_id="t1", scope="user:alice", memory_type=MemoryType.SEMANTIC, content="semantic memory",
    )
    await harness.forgetting_engine.execute("t1", "user:alice", "compliance-officer")
    assert item.vector_ref in harness.vector_db.deleted


async def test_erasure_calls_graph_db_delete_by_source_ref(harness):
    await harness.memory_service.store(tenant_id="t1", scope="agent:a", memory_type=MemoryType.PROCEDURAL, content="proc memory")
    await harness.forgetting_engine.execute("t1", "agent:a", "compliance-officer")
    assert "agent:a" in harness.graph_db.deleted_source_refs


async def test_erasure_of_empty_subject_still_produces_proof(harness):
    record = await harness.forgetting_engine.execute("t1", "user:nobody", "compliance-officer")
    assert record.memory_items_deleted == []
    assert record.deletion_proof_hash == compute_deletion_proof([])


def test_deletion_proof_deterministic_for_same_items():
    from long_term_memory.core.domain import MemoryItemRecord

    items = [
        MemoryItemRecord(id="a", tenant_id="t1", scope="s", memory_type=MemoryType.FACT, content="x"),
        MemoryItemRecord(id="b", tenant_id="t1", scope="s", memory_type=MemoryType.FACT, content="y"),
    ]
    assert compute_deletion_proof(items) == compute_deletion_proof(list(reversed(items)))


def test_deletion_proof_differs_for_different_content():
    from long_term_memory.core.domain import MemoryItemRecord

    a = [MemoryItemRecord(id="a", tenant_id="t1", scope="s", memory_type=MemoryType.FACT, content="x")]
    b = [MemoryItemRecord(id="a", tenant_id="t1", scope="s", memory_type=MemoryType.FACT, content="y")]
    assert compute_deletion_proof(a) != compute_deletion_proof(b)
