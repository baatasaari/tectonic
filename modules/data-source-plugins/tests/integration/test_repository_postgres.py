"""Integration tier (LLD §3 testing plan): the SQLAlchemy repository
against a real Postgres — not part of the default unit-test run. See
`conftest.py` for how the Postgres instance is obtained.

Specifically exercises what SQLite's unit-tier tests can't: real JSONB
round-tripping of an arbitrary connection-config dict (`ConnectorConfig.
connection_config`) and a nested schema-diff dict (`DriftIncident.
schema_diff`), a real UUID primary key round trip, and a multi-row query
(`list_sync_runs`) that must return only the rows for the intended
connector out of several sharing the table.
"""
from __future__ import annotations

import os

import pytest
from alembic.config import Config as AlembicConfig
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from alembic import command
from data_source_plugins.core.domain import (
    ConnectorConfigRecord,
    ConnectorStatus,
    DriftClassification,
    DriftIncidentRecord,
    SyncRunRecord,
    SyncRunStatus,
    new_id,
)
from data_source_plugins.db.repository import SQLAlchemyConnectorRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def migrated_url(postgres_url):
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", postgres_url)
    os.environ["DATA_SOURCE_PLUGINS_DATABASE_URL"] = postgres_url
    command.upgrade(alembic_cfg, "head")
    return postgres_url


async def test_connector_config_round_trips_jsonb_dict_and_real_uuid_pk(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyConnectorRepository(session)
            record = ConnectorConfigRecord(
                id=new_id(), tenant_id="acme", source_type="postgres",
                connection_config={"host": "db.internal", "port": 5432, "ssl": True, "schemas": ["public", "audit"]},
                secrets_ref="secrets/acme/pg", sync_schedule="0 */6 * * *", status=ConnectorStatus.ACTIVE,
            )
            created = await repo.create_connector(record)
            # A real UUID primary key round trip — asyncpg hands back a genuine UUID
            # value that str()s back to the id we set, not just an opaque CHAR(36) blob.
            assert created.id == record.id

            fetched = await repo.get_connector(record.id)
            assert fetched is not None
            # Real JSONB preserves nested types exactly: bool stays bool, int stays int,
            # and the nested list keeps its order — SQLite's JSON-as-TEXT variant has no
            # native type to enforce any of that.
            assert fetched.connection_config == {
                "host": "db.internal", "port": 5432, "ssl": True, "schemas": ["public", "audit"],
            }
            assert fetched.connection_config["ssl"] is True
    finally:
        await engine.dispose()


async def test_list_sync_runs_returns_only_the_matching_connectors_rows(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyConnectorRepository(session)
            connector_a = await repo.create_connector(
                ConnectorConfigRecord(id=new_id(), tenant_id="acme", source_type="postgres")
            )
            connector_b = await repo.create_connector(
                ConnectorConfigRecord(id=new_id(), tenant_id="acme", source_type="s3")
            )

            for status, count in [(SyncRunStatus.COMPLETED, 10), (SyncRunStatus.COMPLETED, 20)]:
                await repo.create_sync_run(
                    SyncRunRecord(id=new_id(), connector_id=connector_a.id, status=status, records_synced=count)
                )
            await repo.create_sync_run(
                SyncRunRecord(id=new_id(), connector_id=connector_b.id, status=SyncRunStatus.FAILED, records_synced=0)
            )

            # A multi-row query must hit only the rows for the intended connector, even
            # though the table has rows for another connector interleaved with them.
            runs_a = await repo.list_sync_runs(connector_a.id)
            assert len(runs_a) == 2
            assert {r.connector_id for r in runs_a} == {connector_a.id}
            assert sorted(r.records_synced for r in runs_a) == [10, 20]

            runs_b = await repo.list_sync_runs(connector_b.id)
            assert len(runs_b) == 1
            assert runs_b[0].status == SyncRunStatus.FAILED
    finally:
        await engine.dispose()


async def test_drift_incident_schema_diff_round_trips_as_nested_jsonb(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyConnectorRepository(session)
            connector = await repo.create_connector(
                ConnectorConfigRecord(id=new_id(), tenant_id="acme", source_type="postgres")
            )
            diff = {
                "added_fields": ["region"],
                "removed_fields": [],
                "type_changes": [{"field": "amount", "from": "int", "to": "float"}],
            }
            created = await repo.create_drift_incident(
                DriftIncidentRecord(
                    id=new_id(), connector_id=connector.id, schema_diff=diff,
                    classification=DriftClassification.TYPE_WIDENING, auto_adapted=True,
                )
            )
            assert created.classification == DriftClassification.TYPE_WIDENING

            incidents, total = await repo.list_drift_incidents(connector.id)
            assert len(incidents) == 1
            assert total == 1
            # A nested dict-of-lists-of-dicts JSONB structure preserved exactly.
            assert incidents[0].schema_diff == diff
            assert incidents[0].schema_diff["type_changes"][0]["to"] == "float"
    finally:
        await engine.dispose()
