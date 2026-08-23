"""Integration tier (LLD §3.1 testing plan): the SQLAlchemy repository
against a real Postgres — not part of the default unit-test run. See
`conftest.py` for how the Postgres instance is obtained.

Specifically exercises what SQLite's unit-tier tests can't: real JSONB
round-tripping of a list-of-dicts with nested structure (`retrieved_items`,
`provenance_chain`) and a plain list-of-strings (`scope`), and a real UUID
primary key round trip on `RetrievalRequest`/`RetrievalHop` — asyncpg
returns/accepts genuine UUID values where SQLite's CHAR(36) variant just
stores an opaque string.
"""
from __future__ import annotations

import os

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from agentic_rag.core.domain import (
    Provenance,
    RetrievalHopRecord,
    RetrievalOutcome,
    RetrievalRequestRecord,
    RetrievalResultRecord,
    RetrievalSource,
    RetrievedItem,
    new_id,
)
from agentic_rag.db.repository import SQLAlchemyRAGRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def migrated_url(postgres_url):
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", postgres_url)
    os.environ["AGENTIC_RAG_DATABASE_URL"] = postgres_url
    command.upgrade(alembic_cfg, "head")
    return postgres_url


async def test_retrieval_request_scope_round_trips_as_real_jsonb_list(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyRAGRepository(session)
            record = RetrievalRequestRecord(
                id=new_id(), tenant_id="acme", query="what is the refund policy?",
                scope=["kb:policies", "kb:legal", "kb:faq"], max_hops=4, groundedness_threshold=0.9,
            )
            created = await repo.create_request(record)
            # A real UUID primary key round trip: asyncpg hands back a genuine UUID
            # value that str()s back to the id we set, not just an opaque CHAR(36) blob.
            assert created.id == record.id

            fetched = await repo.get_request(record.id)
            assert fetched is not None
            # Real JSONB preserves list order and element types; SQLite's JSON-as-TEXT
            # variant can silently reorder or coerce these without a native type to enforce it.
            assert fetched.scope == ["kb:policies", "kb:legal", "kb:faq"]
    finally:
        await engine.dispose()


async def test_retrieval_hop_retrieved_items_round_trip_nested_jsonb(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyRAGRepository(session)
            request = await repo.create_request(
                RetrievalRequestRecord(id=new_id(), tenant_id="acme", query="q")
            )
            items = [
                RetrievedItem(
                    content="refunds are processed within 14 days",
                    source=RetrievalSource.VECTOR_DB,
                    provenance=Provenance(source_document="policy.pdf", version="3", location="p.2"),
                    retrieval_score=0.91,
                ),
                RetrievedItem(
                    content="EU customers get 30 days",
                    source=RetrievalSource.GRAPH_DB,
                    provenance=Provenance(source_document="eu_addendum.pdf"),
                    retrieval_score=0.77,
                ),
            ]
            hop = await repo.create_hop(
                RetrievalHopRecord(
                    id=new_id(), request_id=request.id, hop_number=1,
                    retrieved_items=items, groundedness_score=0.6,
                    reformulated_query="refund policy for EU customers",
                )
            )
            assert hop.id != request.id

            hops = await repo.list_hops(request.id)
            assert len(hops) == 1
            # Nested dict-in-list JSONB: each retrieved item's provenance sub-object,
            # enum-valued source field, and float score must all survive intact and in order.
            fetched_items = hops[0].retrieved_items
            assert [i.content for i in fetched_items] == [
                "refunds are processed within 14 days",
                "EU customers get 30 days",
            ]
            assert fetched_items[0].source == RetrievalSource.VECTOR_DB
            assert fetched_items[0].provenance == Provenance(source_document="policy.pdf", version="3", location="p.2")
            assert fetched_items[1].provenance.source_document == "eu_addendum.pdf"
            assert fetched_items[0].retrieval_score == 0.91
    finally:
        await engine.dispose()


async def test_retrieval_result_provenance_chain_round_trips_as_jsonb(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyRAGRepository(session)
            request = await repo.create_request(
                RetrievalRequestRecord(id=new_id(), tenant_id="acme", query="q2")
            )
            chain = [
                Provenance(source_document="policy.pdf", version="3", location="p.2"),
                Provenance(source_document="eu_addendum.pdf", version="latest", location=""),
            ]
            result = await repo.create_result(
                RetrievalResultRecord(
                    request_id=request.id, final_context="refunds within 14-30 days depending on region",
                    total_hops=2, final_groundedness_score=0.93,
                    provenance_chain=chain, outcome=RetrievalOutcome.SUFFICIENT,
                )
            )
            assert result.outcome == RetrievalOutcome.SUFFICIENT

            fetched = await repo.get_result(request.id)
            assert fetched is not None
            # A list of dict-shaped provenance records preserved exactly, in order.
            assert fetched.provenance_chain == chain
    finally:
        await engine.dispose()
