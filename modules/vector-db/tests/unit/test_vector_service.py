import pytest

from vector_db.config import IsolationConfig
from vector_db.core.domain import PointNotFoundError, QuotaExceededError
from vector_db.core.vector_service import VectorService


async def test_index_and_dense_query_round_trip(harness):
    point_id = await harness.vector_service.index_point(
        tenant_id="t1", source_module="knowledge_base", source_ref="chunk-1",
        content="The quick brown fox jumps over the lazy dog",
    )
    assert point_id

    results = await harness.vector_service.query(tenant_id="t1", text="quick brown fox", hybrid=False)
    assert len(results) == 1
    assert results[0].id == point_id
    assert results[0].payload["source_ref"] == "chunk-1"


async def test_hybrid_query_returns_results(harness):
    await harness.vector_service.index_point(
        tenant_id="t1", source_module="knowledge_base", source_ref="chunk-1", content="apples and oranges",
    )
    await harness.vector_service.index_point(
        tenant_id="t1", source_module="knowledge_base", source_ref="chunk-2", content="rocket ships and stars",
    )

    results = await harness.vector_service.query(tenant_id="t1", text="apples oranges", hybrid=True, top_k=5)
    assert len(results) >= 1


async def test_query_isolates_by_tenant_in_shared_collection_mode(harness):
    await harness.vector_service.index_point(
        tenant_id="tenant-a", source_module="knowledge_base", source_ref="a-1", content="tenant a content",
    )
    await harness.vector_service.index_point(
        tenant_id="tenant-b", source_module="knowledge_base", source_ref="b-1", content="tenant b content",
    )

    results_a = await harness.vector_service.query(tenant_id="tenant-a", text="tenant a content", hybrid=False)
    assert all(r.payload["tenant_id"] == "tenant-a" for r in results_a)


async def test_query_against_unknown_tenant_returns_empty(harness):
    results = await harness.vector_service.query(tenant_id="never-indexed", text="anything", hybrid=False)
    assert results == []


async def test_delete_point_removes_it_from_results(harness):
    point_id = await harness.vector_service.index_point(
        tenant_id="t1", source_module="knowledge_base", source_ref="chunk-1", content="content to delete",
    )
    await harness.vector_service.delete_point("t1", point_id)

    results = await harness.vector_service.query(tenant_id="t1", text="content to delete", hybrid=False)
    assert all(r.id != point_id for r in results)


async def test_delete_point_unknown_tenant_raises(harness):
    with pytest.raises(PointNotFoundError):
        await harness.vector_service.delete_point("never-indexed", "some-id")


async def test_dedicated_collection_tenancy_isolates_physically(harness_factory):
    harness = harness_factory(isolation=IsolationConfig(tenancy_model="dedicated_collection"))
    await harness.vector_service.index_point(
        tenant_id="tenant-a", source_module="knowledge_base", source_ref="a-1", content="alpha content here",
    )
    collections = await harness.client.get_collections()
    names = [c.name for c in collections.collections]
    assert any("tenant-a" in n for n in names)


async def test_quota_exceeded_rejects_before_the_point_is_written(harness):
    harness.multi_tenancy.allowed = False
    harness.multi_tenancy.reason = "vector_count quota exceeded"

    with pytest.raises(QuotaExceededError):
        await harness.vector_service.index_point(
            tenant_id="t1", source_module="knowledge_base", source_ref="chunk-1", content="rejected content",
        )

    results = await harness.vector_service.query(tenant_id="t1", text="rejected content", hybrid=False)
    assert results == []


async def test_quota_check_is_called_with_the_live_current_count(harness):
    await harness.vector_service.index_point(
        tenant_id="t1", source_module="knowledge_base", source_ref="chunk-1", content="first point",
    )
    harness.multi_tenancy.calls.clear()

    await harness.vector_service.index_point(
        tenant_id="t1", source_module="knowledge_base", source_ref="chunk-2", content="second point",
    )

    assert harness.multi_tenancy.calls == [
        {"tenant_id": "t1", "resource_class": "vector_count", "amount": 1.0, "current_usage": 1.0},
    ]


async def test_quota_check_is_scoped_per_tenant(harness):
    await harness.vector_service.index_point(
        tenant_id="tenant-a", source_module="knowledge_base", source_ref="a-1", content="tenant a content",
    )
    harness.multi_tenancy.calls.clear()

    await harness.vector_service.index_point(
        tenant_id="tenant-b", source_module="knowledge_base", source_ref="b-1", content="tenant b content",
    )

    # tenant-b's own first point -- current usage is 0, not tenant-a's 1.
    assert harness.multi_tenancy.calls == [
        {"tenant_id": "tenant-b", "resource_class": "vector_count", "amount": 1.0, "current_usage": 0.0},
    ]


async def test_no_multi_tenancy_client_configured_skips_the_check(harness_factory):
    """multi_tenancy is optional -- a service constructed without one
    keeps working unchanged."""
    harness = harness_factory()
    service = VectorService(
        harness.client, harness.embeddings, harness.base_alias, harness.isolation, harness.query_config,
        "text-embedding-3-small",
    )

    point_id = await service.index_point(
        tenant_id="t1", source_module="knowledge_base", source_ref="chunk-1", content="no quota client",
    )

    assert point_id


async def test_index_point_with_precomputed_vector_skips_embedding_call(harness):
    point_id = await harness.vector_service.index_point(
        tenant_id="t1", source_module="knowledge_base", source_ref="chunk-1",
        vector=[0.1] * 8, content="ignored for embedding but stored in payload",
    )
    assert point_id
    calls_before = len(harness.embeddings.calls)
    # No embed() call should have been made for the dense vector itself
    # (a query still needs to embed the query text, so we check the point
    # was indexed without an embed call for its own content).
    assert calls_before == 0
