"""Integration tier: proves things SQLite's unit-tier fakes can't reliably
prove -- real JSONB round-tripping for the skills list, the JSONB
containment (`@>`) skill filter, and `ORDER BY trust_score DESC NULLS
LAST` against real Postgres. See `conftest.py` for how the Postgres
instance is obtained.
"""
from __future__ import annotations

import os

import pytest
from alembic.config import Config as AlembicConfig
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from agent_cards.core.domain import AgentCardRecord, AgentSkill, new_id
from agent_cards.db.repository import SQLAlchemyAgentCardsRepository
from alembic import command

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def migrated_url(postgres_url):
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", postgres_url)
    os.environ["AGENT_CARDS_DATABASE_URL"] = postgres_url
    command.upgrade(alembic_cfg, "head")
    return postgres_url


async def test_skills_round_trip_as_real_jsonb_with_nested_structure(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyAgentCardsRepository(session)
            skills = [AgentSkill(id="search", name="Search", description="Finds things")]
            card = await repo.create_card(
                AgentCardRecord(id=new_id(), tenant_id="acme", agent_ref="a1", name="a", description="", url="http://a", skills=skills)
            )

            fetched = await repo.get_card(card.id)

            # Real JSONB round trip preserves nested list-of-dict structure and types exactly
            # -- SQLite's JSON-as-TEXT variant can silently get this wrong.
            assert fetched.skills == skills
    finally:
        await engine.dispose()


async def test_skill_id_filter_uses_jsonb_containment(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyAgentCardsRepository(session)
            await repo.create_card(
                AgentCardRecord(
                    id=new_id(), tenant_id="skill-filter-tenant", agent_ref="a1", name="a", description="", url="http://a",
                    skills=[AgentSkill(id="search", name="Search")],
                )
            )
            await repo.create_card(
                AgentCardRecord(
                    id=new_id(), tenant_id="skill-filter-tenant", agent_ref="a2", name="b", description="", url="http://b",
                    skills=[AgentSkill(id="translate", name="Translate")],
                )
            )

            matching, total = await repo.list_cards(tenant_id="skill-filter-tenant", skill_id="search")

            assert total == 1
            assert matching[0].agent_ref == "a1"
    finally:
        await engine.dispose()


async def test_list_cards_orders_by_trust_score_desc_nulls_last(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyAgentCardsRepository(session)
            low = await repo.create_card(
                AgentCardRecord(id=new_id(), tenant_id="rank-tenant", agent_ref="low", name="low", description="", url="http://a")
            )
            unscored = await repo.create_card(
                AgentCardRecord(id=new_id(), tenant_id="rank-tenant", agent_ref="unscored", name="u", description="", url="http://c")
            )
            high = await repo.create_card(
                AgentCardRecord(id=new_id(), tenant_id="rank-tenant", agent_ref="high", name="high", description="", url="http://b")
            )
            low.trust_score = 0.2
            high.trust_score = 0.9
            await repo.update_card(low)
            await repo.update_card(high)

            cards, total = await repo.list_cards(tenant_id="rank-tenant")

            assert total == 3
            assert [c.id for c in cards] == [high.id, low.id, unscored.id]
    finally:
        await engine.dispose()


async def test_unique_constraint_on_tenant_and_agent_ref_is_enforced(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyAgentCardsRepository(session)
            await repo.create_card(
                AgentCardRecord(id=new_id(), tenant_id="acme", agent_ref="dup", name="a", description="", url="http://a")
            )

            with pytest.raises(IntegrityError):
                await repo.create_card(
                    AgentCardRecord(id=new_id(), tenant_id="acme", agent_ref="dup", name="b", description="", url="http://b")
                )
    finally:
        await engine.dispose()
