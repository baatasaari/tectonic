"""Integration tier (LLD §4 testing plan): the SQLAlchemy repository
against a real Postgres — not part of the default unit-test run. See
`conftest.py` for how the Postgres instance is obtained.

Specifically exercises what SQLite's unit-tier tests can't: `IntentTaxonomy`'s
`intents` (a list of dicts, each itself holding a nested `examples` list)
round-tripping through real JSONB alongside a real UUID primary key,
`ClassificationLog.intents_detected` preserving exact float confidence values
and list order, and a multi-row `get_taxonomy_by_version`/`get_active_taxonomy`
query that must select only the intended tenant+version/status row among
several taxonomies.
"""
from __future__ import annotations

import os

import pytest
from alembic.config import Config as AlembicConfig
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from alembic import command
from intent_detection.core.domain import (
    ClassificationLogRecord,
    DetectedIntent,
    IntentDefinition,
    IntentTaxonomyRecord,
    TaxonomyStatus,
    new_id,
)
from intent_detection.db.repository import SQLAlchemyIntentRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def migrated_url(postgres_url):
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", postgres_url)
    os.environ["INTENT_DETECTION_DATABASE_URL"] = postgres_url
    command.upgrade(alembic_cfg, "head")
    return postgres_url


async def test_intent_taxonomy_intents_round_trip_as_real_jsonb_with_real_uuid_pk(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyIntentRepository(session)
            intents = [
                IntentDefinition(name="book_flight", description="wants to book a flight", examples=["book a flight to NYC", "I need a flight"]),
                IntentDefinition(name="cancel_order", description="wants to cancel an order", examples=["cancel my order"]),
            ]
            created = await repo.create_taxonomy(
                IntentTaxonomyRecord(id=new_id(), tenant_id="acme", version=1, intents=intents)
            )
            # A real JSONB round trip preserves nested list-of-dicts structure, key
            # order, and element types exactly — this is exactly the kind of thing
            # SQLite's JSON-as-TEXT variant can silently get away with getting wrong.
            assert created.intents == intents
            assert created.intents[0].examples == ["book a flight to NYC", "I need a flight"]

            # asyncpg returns/accepts a genuine UUID type for the primary key; SQLite's
            # CHAR(36) variant just stores it as a plain string. Confirm it round-trips
            # as a fetchable primary key against real Postgres UUID semantics.
            fetched = await repo.get_taxonomy(created.id)
            assert fetched is not None
            assert fetched.id == created.id
            assert fetched.intents == intents
    finally:
        await engine.dispose()


async def test_classification_log_intents_detected_round_trips_confidence_floats(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyIntentRepository(session)
            detected = [
                DetectedIntent(name="book_flight", confidence=0.873456),
                DetectedIntent(name="cancel_order", confidence=0.021),
            ]
            created = await repo.create_classification_log(
                ClassificationLogRecord(
                    id=new_id(), tenant_id="acme", input_hash="deadbeef" * 8, taxonomy_version=1,
                    intents_detected=detected, fallback_used=False,
                )
            )
            # Exact float precision and list order survive a real JSONB round trip.
            assert created.intents_detected == detected

            fetched = await repo.list_classification_logs("acme", taxonomy_version=1)
            assert len(fetched) == 1
            assert fetched[0].intents_detected == detected
            assert fetched[0].intents_detected[0].confidence == 0.873456
    finally:
        await engine.dispose()


async def test_get_taxonomy_by_version_and_active_taxonomy_select_only_intended_row(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyIntentRepository(session)
            v1 = await repo.create_taxonomy(
                IntentTaxonomyRecord(id=new_id(), tenant_id="widgetco", version=1, intents=[], status=TaxonomyStatus.DEPRECATED)
            )
            v2 = await repo.create_taxonomy(
                IntentTaxonomyRecord(id=new_id(), tenant_id="widgetco", version=2, intents=[], status=TaxonomyStatus.DRAFT)
            )
            await repo.create_taxonomy(
                IntentTaxonomyRecord(id=new_id(), tenant_id="other-tenant", version=1, intents=[], status=TaxonomyStatus.ACTIVE)
            )
            await repo.activate_taxonomy(v2.id)

            # A multi-row query against real Postgres must select exactly the row
            # matching both the tenant and the version predicate.
            fetched_v1 = await repo.get_taxonomy_by_version("widgetco", 1)
            assert fetched_v1 is not None
            assert fetched_v1.id == v1.id
            assert fetched_v1.version == 1

            # get_active_taxonomy must pick widgetco's active row, never the other
            # tenant's active taxonomy or widgetco's own deprecated v1.
            active = await repo.get_active_taxonomy("widgetco")
            assert active is not None
            assert active.id == v2.id
            assert active.status == TaxonomyStatus.ACTIVE
    finally:
        await engine.dispose()
