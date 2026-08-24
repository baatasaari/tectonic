"""Pagination behavior for InMemoryKnowledgeBaseRepository's chunk listers."""
from __future__ import annotations

import pytest

from knowledge_base.core.domain import (
    ChunkRecord,
    DocumentRecord,
    DocumentVersionRecord,
    SourceType,
)
from knowledge_base.core.fakes import InMemoryKnowledgeBaseRepository


def _chunk(document_version_id: str, chunk_index: int, policy_tags: list[str] | None = None) -> ChunkRecord:
    return ChunkRecord(
        id=f"chunk-{document_version_id}-{chunk_index}",
        document_version_id=document_version_id,
        content=f"content {chunk_index}",
        chunk_index=chunk_index,
        policy_tags=policy_tags or [],
    )


@pytest.mark.asyncio
async def test_list_chunks_by_version_paginates_in_chunk_index_order():
    repo = InMemoryKnowledgeBaseRepository()
    await repo.create_chunks([_chunk("v1", i) for i in (0, 1, 2)])

    page1, total1 = await repo.list_chunks_by_version("v1", limit=2, offset=0)
    assert total1 == 3
    assert [c.chunk_index for c in page1] == [0, 1]

    page2, total2 = await repo.list_chunks_by_version("v1", limit=2, offset=2)
    assert total2 == 3
    assert [c.chunk_index for c in page2] == [2]


@pytest.mark.asyncio
async def test_list_chunks_by_version_empty_result_set():
    repo = InMemoryKnowledgeBaseRepository()
    items, total = await repo.list_chunks_by_version("no-such-version")
    assert items == []
    assert total == 0


@pytest.mark.asyncio
async def test_list_chunks_by_policy_tag_paginates():
    repo = InMemoryKnowledgeBaseRepository()
    document = await repo.create_document(
        DocumentRecord(id="d1", tenant_id="tenant-a", title="Doc", source_type=SourceType.UPLOAD)
    )
    version = await repo.create_version(
        DocumentVersionRecord(id="v1", document_id=document.id, content_hash="h", blob_ref="b", version_number=1)
    )
    await repo.create_chunks(
        [_chunk(version.id, i, policy_tags=["internal"]) for i in (0, 1, 2)]
    )
    # A chunk without the tag should never be returned.
    await repo.create_chunks([_chunk(version.id, 3, policy_tags=["public"])])

    page1, total1 = await repo.list_chunks_by_policy_tag("tenant-a", "internal", limit=2, offset=0)
    assert total1 == 3
    assert [c.chunk_index for c in page1] == [0, 1]

    page2, total2 = await repo.list_chunks_by_policy_tag("tenant-a", "internal", limit=2, offset=2)
    assert total2 == 3
    assert [c.chunk_index for c in page2] == [2]


@pytest.mark.asyncio
async def test_list_chunks_by_policy_tag_empty_result_set():
    repo = InMemoryKnowledgeBaseRepository()
    items, total = await repo.list_chunks_by_policy_tag("tenant-with-nothing", "internal")
    assert items == []
    assert total == 0
