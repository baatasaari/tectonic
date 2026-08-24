"""Integration tier: proves things SQLite's unit-tier fakes can't reliably
prove -- real JSONB round-tripping for the skills snapshot, real
`COUNT`/`COUNT DISTINCT` usage-event aggregation, and `ORDER BY
reuse_count DESC, trust_score_snapshot DESC NULLS LAST` against real
Postgres. See `conftest.py` for how the Postgres instance is obtained.
"""
from __future__ import annotations

import os

import pytest
from alembic.config import Config as AlembicConfig
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from agent_marketplace.core.domain import ListingRecord, ListingStatus, UsageEventRecord, new_id
from agent_marketplace.db.repository import SQLAlchemyAgentMarketplaceRepository
from alembic import command

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def migrated_url(postgres_url):
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", postgres_url)
    os.environ["AGENT_MARKETPLACE_DATABASE_URL"] = postgres_url
    command.upgrade(alembic_cfg, "head")
    return postgres_url


async def test_skills_snapshot_round_trips_as_real_jsonb_with_nested_structure(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyAgentMarketplaceRepository(session)
            skills = [{"id": "search", "name": "Search", "description": "Finds things", "extra": {"nested": [1, 2]}}]
            listing = await repo.create_listing(
                ListingRecord(
                    id=new_id(), tenant_id="acme", agent_card_id="card-1", name="a", description="",
                    skills_snapshot=skills,
                )
            )

            fetched = await repo.get_listing(listing.id)

            # Real JSONB round trip preserves nested dict/list structure and types exactly
            # -- SQLite's JSON-as-TEXT variant can silently get this wrong.
            assert fetched.skills_snapshot == skills
    finally:
        await engine.dispose()


async def test_usage_event_counts_total_vs_distinct_consumer_tenants(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyAgentMarketplaceRepository(session)
            listing = await repo.create_listing(
                ListingRecord(id=new_id(), tenant_id="acme", agent_card_id="card-1", name="a", description="")
            )
            for tenant in ("globex", "globex", "initech"):
                await repo.create_usage_event(
                    UsageEventRecord(id=new_id(), listing_id=listing.id, consumer_tenant_id=tenant)
                )

            total, distinct = await repo.count_usage_events(listing.id)

            assert total == 3
            assert distinct == 2
    finally:
        await engine.dispose()


async def test_list_listings_orders_by_reuse_count_then_trust_score_desc_nulls_last(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyAgentMarketplaceRepository(session)
            low = await repo.create_listing(
                ListingRecord(
                    id=new_id(), tenant_id="rank-tenant", agent_card_id="c1", name="low", description="",
                    status=ListingStatus.PUBLISHED, reuse_count=1, trust_score_snapshot=0.9,
                )
            )
            high = await repo.create_listing(
                ListingRecord(
                    id=new_id(), tenant_id="rank-tenant", agent_card_id="c2", name="high", description="",
                    status=ListingStatus.PUBLISHED, reuse_count=5, trust_score_snapshot=0.1,
                )
            )
            unscored = await repo.create_listing(
                ListingRecord(
                    id=new_id(), tenant_id="rank-tenant", agent_card_id="c3", name="unscored", description="",
                    status=ListingStatus.PUBLISHED, reuse_count=1, trust_score_snapshot=None,
                )
            )

            listings, total = await repo.list_listings(tenant_id="rank-tenant", status=ListingStatus.PUBLISHED)

            assert total == 3
            # reuse_count wins first (high=5 beats everyone); among reuse_count=1, trust_score
            # DESC NULLS LAST puts the scored one (low, 0.9) before the unscored one.
            assert [listing.id for listing in listings] == [high.id, low.id, unscored.id]
    finally:
        await engine.dispose()
