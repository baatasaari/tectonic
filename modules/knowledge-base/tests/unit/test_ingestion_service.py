from datetime import UTC, datetime, timedelta

import pytest

from knowledge_base.core.domain import DocumentNotFoundError, DocumentStatus, SourceType


async def test_ingest_document_creates_document_version_and_chunks(harness):
    text = " ".join([f"word{i}" for i in range(30)])
    result = await harness.service.ingest_document(
        tenant_id="t1", title="My Doc", source_type=SourceType.UPLOAD, content=text.encode(),
        policy_tags=["internal"], chunking_strategy="fixed_size",
    )

    assert result.document.title == "My Doc"
    assert result.version.version_number == 1
    assert result.chunk_count > 0

    chunks, total = await harness.repository.list_chunks_by_version(result.version.id)
    assert len(chunks) == result.chunk_count
    assert total == result.chunk_count
    assert all(c.policy_tags == ["internal"] for c in chunks)

    assert len(harness.vector_db.stored) == result.chunk_count
    assert len(harness.graph_db.extracted) == result.chunk_count


async def test_ingest_document_sets_current_version_on_document(harness):
    result = await harness.service.ingest_document(
        tenant_id="t1", title="Doc", source_type=SourceType.UPLOAD, content=b"hello world",
    )
    document = await harness.repository.get_document(result.document.id)
    assert document.current_version_id == result.version.id


async def test_create_version_increments_version_number(harness):
    first = await harness.service.ingest_document(
        tenant_id="t1", title="Doc", source_type=SourceType.UPLOAD, content=b"version one content",
    )
    second = await harness.service.create_version(first.document.id, content=b"version two content, changed")

    assert second.version.version_number == 2
    document = await harness.repository.get_document(first.document.id)
    assert document.current_version_id == second.version.id


async def test_create_version_dedups_identical_content(harness):
    first = await harness.service.ingest_document(
        tenant_id="t1", title="Doc", source_type=SourceType.UPLOAD, content=b"identical content",
    )
    second = await harness.service.create_version(first.document.id, content=b"identical content")

    assert second.version.id == first.version.id
    assert second.version.version_number == 1
    versions = await harness.repository.list_versions(first.document.id)
    assert len(versions) == 1


async def test_create_version_unknown_document_raises(harness):
    with pytest.raises(DocumentNotFoundError):
        await harness.service.create_version("missing", content=b"x")


async def test_review_resets_stale_to_active(harness):
    result = await harness.service.ingest_document(
        tenant_id="t1", title="Doc", source_type=SourceType.UPLOAD, content=b"content",
    )
    document = await harness.repository.get_document(result.document.id)
    document.status = DocumentStatus.STALE
    await harness.repository.update_document(document)

    reviewed = await harness.service.review(result.document.id, "alice")
    assert reviewed.status == DocumentStatus.ACTIVE


async def test_run_staleness_sweep_flags_old_documents(harness):
    result = await harness.service.ingest_document(
        tenant_id="t1", title="Old Doc", source_type=SourceType.UPLOAD, content=b"content",
    )
    document = await harness.repository.get_document(result.document.id)
    document.last_reviewed_at = datetime.now(UTC) - timedelta(days=999)
    await harness.repository.update_document(document)

    report = await harness.service.run_staleness_sweep("t1")
    assert result.document.id in report.stale_document_ids

    updated = await harness.repository.get_document(result.document.id)
    assert updated.status == DocumentStatus.STALE


async def test_run_staleness_sweep_disabled_returns_empty(harness_factory):
    from knowledge_base.config import StalenessConfig

    harness = harness_factory(staleness_config=StalenessConfig(auto_flag_enabled=False))
    await harness.service.ingest_document(
        tenant_id="t1", title="Doc", source_type=SourceType.UPLOAD, content=b"content",
    )
    report = await harness.service.run_staleness_sweep("t1")
    assert report.stale_document_ids == []
