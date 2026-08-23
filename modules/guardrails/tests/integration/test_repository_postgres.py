"""Integration tier (LLD §4 testing plan): the SQLAlchemy repository
against a real Postgres — not part of the default unit-test run. See
`conftest.py` for how the Postgres instance is obtained.

Specifically exercises what SQLite's unit-tier tests can't: real JSONB
list round-tripping across three separate columns on `PolicyProfile`
(`enabled_checks`, `pii_entity_types`, `denied_topics`), a real UUID
foreign key (`BypassIncident.red_team_run_id`) that must scope a
multi-row query to only the intended parent run, and an `ORDER BY ...
LIMIT 1` query across multiple rows against genuine Postgres semantics.
"""
from __future__ import annotations

import os

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from guardrails.core.domain import BypassIncidentRecord, PolicyProfileRecord, RedTeamRunRecord, new_id
from guardrails.db.repository import SQLAlchemyGuardrailsRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def migrated_url(postgres_url):
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", postgres_url)
    os.environ["GUARDRAILS_DATABASE_URL"] = postgres_url
    command.upgrade(alembic_cfg, "head")
    return postgres_url


async def test_policy_profile_json_lists_round_trip_as_real_jsonb(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyGuardrailsRepository(session)
            enabled_checks = ["jailbreak_detection", "pii_detection", "groundedness_check"]
            pii_entity_types = ["EMAIL", "CREDIT_CARD", "SSN"]
            denied_topics = ["weapons", "self_harm"]
            created = await repo.create_policy_profile(
                PolicyProfileRecord(
                    id=new_id(), tenant_id="acme", name="strict", enabled_checks=enabled_checks,
                    pii_entity_types=pii_entity_types, denied_topics=denied_topics,
                )
            )
            assert created.enabled_checks == enabled_checks

            # A real JSONB round trip preserves list order and element types exactly on
            # every column, not just one — this is exactly the kind of thing SQLite's
            # JSON-as-TEXT variant can silently get away with getting wrong that
            # Postgres's native JSONB won't.
            fetched = await repo.get_policy_profile("acme", created.id)
            assert fetched is not None
            assert fetched.enabled_checks == enabled_checks
            assert fetched.pii_entity_types == pii_entity_types
            assert fetched.denied_topics == denied_topics
    finally:
        await engine.dispose()


async def test_bypass_incidents_scoped_by_real_uuid_run_fk(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyGuardrailsRepository(session)
            run_a = await repo.create_red_team_run(
                RedTeamRunRecord(id=new_id(), tenant_id="acme", attempts_generated=10, successful_bypasses=2)
            )
            run_b = await repo.create_red_team_run(
                RedTeamRunRecord(id=new_id(), tenant_id="acme", attempts_generated=8, successful_bypasses=1)
            )
            incident_a1 = await repo.create_bypass_incident(
                BypassIncidentRecord(
                    id=new_id(), red_team_run_id=run_a.id, attack_pattern="dan_prompt", target_check="jailbreak_detection",
                )
            )
            incident_a2 = await repo.create_bypass_incident(
                BypassIncidentRecord(
                    id=new_id(), red_team_run_id=run_a.id, attack_pattern="roleplay_bypass", target_check="pii_detection",
                )
            )
            await repo.create_bypass_incident(
                BypassIncidentRecord(
                    id=new_id(), red_team_run_id=run_b.id, attack_pattern="unicode_smuggle", target_check="jailbreak_detection",
                )
            )

            # a real UUID foreign key (asyncpg returns/accepts a genuine UUID type;
            # SQLite's CHAR(36) variant just stores it as a plain string) — confirm the
            # multi-row query hits only the incidents belonging to run_a, not run_b's.
            incidents = await repo.list_bypass_incidents(run_a.id)
            assert {i.id for i in incidents} == {incident_a1.id, incident_a2.id}
            assert all(i.red_team_run_id == run_a.id for i in incidents)
    finally:
        await engine.dispose()


async def test_get_default_policy_profile_orders_across_multiple_active_rows(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyGuardrailsRepository(session)
            # a tenant distinct from the other tests in this module, so this test's
            # ordering assertion isn't polluted by profiles those tests created.
            first = await repo.create_policy_profile(
                PolicyProfileRecord(id=new_id(), tenant_id="default-tenant", name="first", status="active")
            )
            await repo.create_policy_profile(
                PolicyProfileRecord(id=new_id(), tenant_id="default-tenant", name="second", status="active")
            )
            await repo.create_policy_profile(
                PolicyProfileRecord(
                    id=new_id(), tenant_id="default-tenant", name="inactive-but-earlier", status="disabled"
                )
            )

            # ORDER BY created_at LIMIT 1 across multiple candidate rows — must pick the
            # earliest-created active profile, not just any matching row.
            default = await repo.get_default_policy_profile("default-tenant")
            assert default is not None
            assert default.id == first.id
    finally:
        await engine.dispose()
