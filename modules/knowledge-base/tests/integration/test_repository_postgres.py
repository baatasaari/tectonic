"""Integration tier (LLD §3 testing plan): the SQLAlchemy repository
against a real Postgres — not part of the default unit-test run. See
`conftest.py` for how the Postgres instance is obtained.

Specifically exercises what SQLite's unit-tier tests can't: a genuine
multi-row bulk insert (`create_chunks`) producing distinct real UUID
primary keys per row with each chunk's `policy_tags` JSONB list preserved
exactly, and a multi-table, multi-row filter query
(`list_chunks_by_policy_tag`) that must return only the chunks tagged with
the requested policy across several documents/versions/chunks sharing the
same tables.
"""
from __future__ import annotations

import os
from datetime import datetime

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from knowledge_base.core.domain import (
    ChunkRecord,
    DocumentRecord,
    DocumentVersionRecord,
    SourceType,
    new_id,
)
from knowledge_base.db.repository import SQLAlchemyKnowledgeBaseRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def migrated_url(postgres_url):
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", postgres_url)
    os.environ["KNOWLEDGE_BASE_DATABASE_URL"] = postgres_url
    command.upgrade(alembic_cfg, "head")
    return postgres_url


async def _make_document_version(repo, tenant_id: str) -> DocumentVersionRecord:
    document = await repo.create_document(
        DocumentRecord(
            id=new_id(), tenant_id=tenant_id, title="doc", source_type=SourceType.UPLOAD,
            # The Document model's last_reviewed_at column is a naive TIMESTAMP; the
            # domain default (tz-aware UTC via now()) is deliberately not used here.
            last_reviewed_at=datetime(2024, 1, 1),
        )
    )
    return await repo.create_version(
        DocumentVersionRecord(
            id=new_id(), document_id=document.id, content_hash="abc123", blob_ref="blobs/x", version_number=1,
        )
    )


async def test_create_chunks_bulk_inserts_distinct_rows_with_uuid_pks_and_jsonb_tags(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyKnowledgeBaseRepository(session)
            version = await _make_document_version(repo, "acme")

            records = [
                ChunkRecord(
                    id=new_id(), document_version_id=version.id, content=f"chunk {i}",
                    chunk_index=i, policy_tags=["pii", "internal_only"] if i == 0 else ["public"],
                    token_count=10 + i,
                )
                for i in range(3)
            ]
            created = await repo.create_chunks(records)

            # A genuine multi-row bulk insert: three distinct real UUID primary keys,
            # not one id reused three times the way a naive fake might let slip through.
            assert len({c.id for c in created}) == 3
            assert {c.id for c in created} == {r.id for r in records}

            fetched = await repo.list_chunks_by_version(version.id)
            assert len(fetched) == 3
            assert [c.chunk_index for c in fetched] == [0, 1, 2]
            # Real JSONB list preserved exactly, per row, including order.
            assert fetched[0].policy_tags == ["pii", "internal_only"]
            assert fetched[1].policy_tags == ["public"]
    finally:
        await engine.dispose()


async def test_list_chunks_by_policy_tag_returns_only_matching_rows_across_documents(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyKnowledgeBaseRepository(session)
            # A tenant distinct from the other tests in this module: list_chunks_by_policy_tag
            # scans all of the tenant's documents, so sharing a tenant id with another test's
            # data in the same database would make this assertion spuriously fragile.
            tenant_id = "acme-policy-tag-test"
            version_a = await _make_document_version(repo, tenant_id)
            version_b = await _make_document_version(repo, tenant_id)

            await repo.create_chunks([
                ChunkRecord(id=new_id(), document_version_id=version_a.id, content="a0", chunk_index=0, policy_tags=["pii"]),
                ChunkRecord(id=new_id(), document_version_id=version_a.id, content="a1", chunk_index=1, policy_tags=["public"]),
            ])
            await repo.create_chunks([
                ChunkRecord(id=new_id(), document_version_id=version_b.id, content="b0", chunk_index=0, policy_tags=["pii", "financial"]),
                ChunkRecord(id=new_id(), document_version_id=version_b.id, content="b1", chunk_index=1, policy_tags=["public"]),
            ])

            # A multi-table, multi-row filter: only the two chunks tagged "pii" across
            # both documents/versions should come back — the "public"-tagged chunks in
            # the same tables must not leak into the result.
            matching = await repo.list_chunks_by_policy_tag(tenant_id, "pii")
            assert {c.content for c in matching} == {"a0", "b0"}
            assert len(matching) == 2

            other = await repo.list_chunks_by_policy_tag(tenant_id, "financial")
            assert [c.content for c in other] == ["b0"]
    finally:
        await engine.dispose()


async def test_document_current_version_id_round_trips_as_real_uuid(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyKnowledgeBaseRepository(session)
            document = await repo.create_document(
                DocumentRecord(
                    id=new_id(), tenant_id="acme", title="policy.pdf", source_type=SourceType.UPLOAD,
                    last_reviewed_at=datetime(2024, 1, 1),
                )
            )
            version = await repo.create_version(
                DocumentVersionRecord(
                    id=new_id(), document_id=document.id, content_hash="h1", blob_ref="blobs/v1", version_number=1,
                )
            )
            document.current_version_id = version.id
            updated = await repo.update_document(document)
            # The FK-shaped current_version_id must round-trip as the exact same real
            # UUID primary key that create_version generated, not a lossy string copy.
            assert updated.current_version_id == version.id

            fetched = await repo.get_document(document.id)
            assert fetched is not None
            assert fetched.current_version_id == version.id
    finally:
        await engine.dispose()
