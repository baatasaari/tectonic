import pytest

from vector_db.core import qdrant_ops
from vector_db.core.domain import MigrationNotFoundError, MigrationStatus


async def test_start_with_no_indexed_data_completes_immediately(harness):
    record = await harness.migration_manager.start("never-indexed", "new-model-v2")
    assert record.status == MigrationStatus.COMPLETED
    assert record.points_total == 0


async def test_migration_reembeds_all_points_and_cuts_over_alias(harness):
    alias = harness.base_alias
    texts = ["first document about oceans", "second document about mountains", "third document about deserts"]
    for i, text in enumerate(texts):
        await harness.vector_service.index_point(
            tenant_id="t1", source_module="knowledge_base", source_ref=f"chunk-{i}", content=text,
        )

    before_physical = await qdrant_ops.resolve_alias(harness.client, alias)
    assert before_physical is not None

    record = await harness.migration_manager.start("t1", "new-model-v2")
    assert record.status == MigrationStatus.RUNNING
    assert record.points_total == 3

    completed = await harness.migration_manager.run(record.id)
    assert completed.status == MigrationStatus.COMPLETED
    assert completed.points_migrated == 3

    after_physical = await qdrant_ops.resolve_alias(harness.client, alias)
    assert after_physical == completed.target_collection
    assert after_physical != before_physical

    # The old physical collection was pruned once the cutover verified.
    assert await harness.client.collection_exists(before_physical) is False

    # Queries still work seamlessly post-migration.
    results = await harness.vector_service.query(tenant_id="t1", text="oceans", hybrid=False)
    assert any(r.payload["source_ref"] == "chunk-0" for r in results)

    # New points carry the new embedding_model_version.
    for r in results:
        assert r.payload["embedding_model_version"] == "new-model-v2"


async def test_run_on_unknown_migration_raises(harness):
    with pytest.raises(MigrationNotFoundError):
        await harness.migration_manager.run("does-not-exist")


async def test_get_unknown_migration_raises(harness):
    with pytest.raises(MigrationNotFoundError):
        await harness.migration_manager.get("does-not-exist")


async def test_run_is_a_noop_on_already_completed_migration(harness):
    record = await harness.migration_manager.start("never-indexed", "new-model-v2")
    result = await harness.migration_manager.run(record.id)
    assert result.status == MigrationStatus.COMPLETED
    assert result.points_migrated == 0


async def test_migration_progress_ratio_reaches_one(harness):
    for i in range(5):
        await harness.vector_service.index_point(
            tenant_id="t1", source_module="knowledge_base", source_ref=f"c-{i}", content=f"content number {i}",
        )
    record = await harness.migration_manager.start("t1", "new-model-v2")
    completed = await harness.migration_manager.run(record.id)
    assert completed.progress_ratio == 1.0
