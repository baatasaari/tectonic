"""Integration tier (LLD §3.1 testing plan): the SQLAlchemy repository
against a real Postgres — not part of the default unit-test run. See
`conftest.py` for how the Postgres instance is obtained.

Specifically exercises what SQLite's unit-tier tests can't: real JSONB
round-tripping of plain string lists (`OntologyConfig.roles/entity_types/
policy_tags`), a real dict-of-floats JSONB column (`PrioritisationWeights.
feature_weights`) surviving an upsert without spawning a duplicate row for
the same `(tenant_id, task_type)`, and nested list-of-dict JSONB
(`ContextAssembly.items_included/dropped/summarised`) alongside a real UUID
primary key.
"""
from __future__ import annotations

import os

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from context_engineering.core.domain import (
    AssembledItem,
    ContextAssemblyRecord,
    ItemDisposition,
    OntologyConfigRecord,
    PrioritisationWeightsRecord,
    new_id,
)
from context_engineering.db import models
from context_engineering.db.repository import SQLAlchemyContextRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def migrated_url(postgres_url):
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", postgres_url)
    os.environ["CONTEXT_ENGINEERING_DATABASE_URL"] = postgres_url
    command.upgrade(alembic_cfg, "head")
    return postgres_url


async def test_ontology_config_lists_round_trip_as_real_jsonb(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyContextRepository(session)
            record = OntologyConfigRecord(
                id=new_id(), tenant_id="acme", version=1,
                roles=["analyst", "manager", "auditor"],
                entity_types=["invoice", "contract"],
                policy_tags=["pii", "financial", "internal_only"],
            )
            created = await repo.create_ontology(record)
            # Real UUID primary key round trip.
            assert created.id == record.id

            fetched = await repo.get_active_ontology("acme")
            assert fetched is not None
            # Real JSONB preserves list order and element types across three separate
            # columns — SQLite's JSON-as-TEXT variant can silently get this wrong.
            assert fetched.roles == ["analyst", "manager", "auditor"]
            assert fetched.entity_types == ["invoice", "contract"]
            assert fetched.policy_tags == ["pii", "financial", "internal_only"]
    finally:
        await engine.dispose()


async def test_upsert_weights_updates_only_the_matching_row_not_a_duplicate(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyContextRepository(session)
            first = await repo.upsert_weights(
                PrioritisationWeightsRecord(
                    id=new_id(), tenant_id="acme", task_type="summarisation",
                    feature_weights={"recency": 0.4, "relevance": 0.6},
                )
            )
            second = await repo.upsert_weights(
                PrioritisationWeightsRecord(
                    id=new_id(), tenant_id="acme", task_type="summarisation",
                    feature_weights={"recency": 0.2, "relevance": 0.5, "authority": 0.3},
                )
            )
            # The upsert must reuse the existing row for this (tenant_id, task_type),
            # not insert a second one — the primary key stays the original row's id.
            assert second.id == first.id

            rows = await session.execute(
                select(func.count()).select_from(models.PrioritisationWeights).where(
                    models.PrioritisationWeights.tenant_id == "acme",
                    models.PrioritisationWeights.task_type == "summarisation",
                )
            )
            assert rows.scalar_one() == 1

            fetched = await repo.get_weights("acme", "summarisation")
            assert fetched is not None
            # A real JSONB dict-of-floats round trip, exact keys and values, not just
            # "some JSON-ish text" that happens to parse back similarly.
            assert fetched.feature_weights == {"recency": 0.2, "relevance": 0.5, "authority": 0.3}
    finally:
        await engine.dispose()


async def test_context_assembly_log_round_trips_nested_jsonb_and_uuid_pk(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyContextRepository(session)
            included = [
                AssembledItem(source="agentic_rag", content="refund policy excerpt", tokens=120, disposition=ItemDisposition.INCLUDED),
                AssembledItem(source="short_term_memory", content="user said they're in the EU", tokens=15, disposition=ItemDisposition.INCLUDED),
            ]
            dropped = [
                AssembledItem(source="long_term_memory", content="unrelated ticket #482", tokens=80, disposition=ItemDisposition.DROPPED),
            ]
            summarised = [
                AssembledItem(source="workflow_context", content="prior 6 turns condensed", tokens=40, disposition=ItemDisposition.SUMMARISED),
            ]
            record = ContextAssemblyRecord(
                id=new_id(), request_ref="req-123", task_type="summarisation",
                items_included=included, items_dropped=dropped, items_summarised=summarised,
                total_tokens_used=175,
            )
            created = await repo.create_assembly_log(record)

            assert created.id == record.id
            # Nested list-of-dict JSONB across three separate columns, each preserving
            # order, string content, and integer token counts exactly.
            assert [i.source for i in created.items_included] == ["agentic_rag", "short_term_memory"]
            assert [i.tokens for i in created.items_included] == [120, 15]
            assert created.items_dropped[0].content == "unrelated ticket #482"
            assert created.items_summarised[0].source == "workflow_context"
            assert created.total_tokens_used == 175
    finally:
        await engine.dispose()
