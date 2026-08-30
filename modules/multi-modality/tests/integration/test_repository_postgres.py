"""Integration tier: proves things SQLite's unit-tier fakes can't reliably
prove -- filtering by tenant/modality and pagination ordering round-tripping
through real Postgres. See `conftest.py` for how the Postgres instance is
obtained.
"""
from __future__ import annotations

import os

import pytest
from alembic.config import Config as AlembicConfig
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from alembic import command
from multi_modality.core.domain import ExtractionRecord, GroundednessDecision, Modality, new_id
from multi_modality.db.repository import SQLAlchemyMultiModalityRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def migrated_url(postgres_url):
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", postgres_url)
    os.environ["MULTI_MODALITY_DATABASE_URL"] = postgres_url
    command.upgrade(alembic_cfg, "head")
    return postgres_url


async def test_create_and_get_extraction_round_trip(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyMultiModalityRepository(session)
            created = await repo.create_extraction(
                ExtractionRecord(
                    id=new_id(), tenant_id="acme", modality=Modality.DOCUMENT, raw_content="raw text",
                    extracted_content="raw text", grounding_context="reference",
                    groundedness_decision=GroundednessDecision.BLOCK, groundedness_violation_category="ungrounded",
                    latency_ms=12.5,
                )
            )

            fetched = await repo.get_extraction(created.id)
            assert fetched is not None
            assert fetched.modality == Modality.DOCUMENT
            assert fetched.groundedness_decision == GroundednessDecision.BLOCK
            assert fetched.groundedness_violation_category == "ungrounded"
    finally:
        await engine.dispose()


async def test_list_extractions_filters_by_tenant_and_modality(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyMultiModalityRepository(session)
            await repo.create_extraction(
                ExtractionRecord(
                    id=new_id(), tenant_id="filter-tenant", modality=Modality.VOICE, raw_content="a",
                    extracted_content="a",
                )
            )
            await repo.create_extraction(
                ExtractionRecord(
                    id=new_id(), tenant_id="filter-tenant", modality=Modality.TEXT, raw_content="b",
                    extracted_content="b",
                )
            )
            await repo.create_extraction(
                ExtractionRecord(
                    id=new_id(), tenant_id="other-tenant", modality=Modality.VOICE, raw_content="c",
                    extracted_content="c",
                )
            )

            voice_only, total = await repo.list_extractions(tenant_id="filter-tenant", modality=Modality.VOICE)

            assert total == 1
            assert voice_only[0].raw_content == "a"
    finally:
        await engine.dispose()


async def test_list_extractions_paginates(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyMultiModalityRepository(session)
            for i in range(5):
                await repo.create_extraction(
                    ExtractionRecord(
                        id=new_id(), tenant_id="page-tenant", modality=Modality.TEXT, raw_content=str(i),
                        extracted_content=str(i),
                    )
                )

            page1, total1 = await repo.list_extractions(tenant_id="page-tenant", limit=2, offset=0)
            page2, total2 = await repo.list_extractions(tenant_id="page-tenant", limit=2, offset=2)

            assert total1 == total2 == 5
            assert len(page1) == 2
            assert len(page2) == 2
            assert {e.id for e in page1}.isdisjoint({e.id for e in page2})
    finally:
        await engine.dispose()
