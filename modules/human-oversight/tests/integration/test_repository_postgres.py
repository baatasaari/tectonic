"""Integration tier (LLD's own testing plan): the SQLAlchemy repository
against a real Postgres — not part of the default unit-test run. See
`conftest.py` for how the Postgres instance is obtained.

Specifically exercises what SQLite's unit-tier tests can't: real JSONB
round-tripping of nested dict/list context payloads (`OversightRequest.
context`, and the paired `original_agent_proposal`/`human_override_action`
columns on `OverrideRecordModel`), a real UUID primary key round trip
through `get_request`, and a multi-row filtered query
(`list_pending_expired`) that must hit only the rows matching tenant,
status *and* expiry cutoff — not every row in the table.
"""
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from human_oversight.core.domain import (
    DecisionRecord,
    DecisionType,
    OverrideRecord,
    OversightRequestRecord,
    RequestStatus,
    new_id,
)
from human_oversight.db.repository import SQLAlchemyHumanOversightRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def migrated_url(postgres_url):
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", postgres_url)
    os.environ["HUMAN_OVERSIGHT_DATABASE_URL"] = postgres_url
    command.upgrade(alembic_cfg, "head")
    return postgres_url


async def test_request_context_round_trips_as_real_jsonb_with_real_uuid_pk(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyHumanOversightRepository(session)
            context = {
                "agent_proposal": {"action": "transfer_funds", "amount_cents": 250_00},
                "risk_flags": ["high_value", "new_payee"],
                "auto_approved": False,
                "score": 0.87,
            }
            record = OversightRequestRecord(
                id=new_id(), tenant_id="acme", requesting_module="workflow_engine",
                requesting_ref="wf-1:approval-1", context=context,
            )
            created = await repo.create_request(record)
            # A real JSONB round trip preserves nested dict/list structure and element
            # types exactly — SQLite's JSON-as-TEXT variant can silently get this wrong
            # in ways that don't show up until you're on real Postgres.
            assert created.context == context

            # A real UUID (asyncpg returns/accepts a genuine UUID type; SQLite's CHAR(36)
            # variant just stores it as a plain string) — confirm it round-trips as a
            # fetchable primary key, not just a string that happens to look like one.
            fetched = await repo.get_request("acme", created.id)
            assert fetched is not None
            assert fetched.id == created.id
            assert fetched.context == context
    finally:
        await engine.dispose()


async def test_override_record_dual_jsonb_columns_round_trip_independently(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyHumanOversightRepository(session)
            request = await repo.create_request(
                OversightRequestRecord(
                    id=new_id(), tenant_id="acme", requesting_module="tool_orchestration",
                    requesting_ref="ref-1",
                )
            )
            decision = await repo.create_decision(
                DecisionRecord(
                    id=new_id(), request_id=request.id, decision=DecisionType.OVERRIDE,
                    decided_by="reviewer@acme.example", decision_reason="policy override",
                )
            )
            agent_proposal = {"tool": "send_email", "args": {"to": ["a@x.com", "b@x.com"], "cc": []}}
            human_action = {"tool": "send_email", "args": {"to": ["a@x.com"], "cc": []}, "blocked": ["b@x.com"]}
            override = await repo.create_override_record(
                OverrideRecord(
                    id=new_id(), decision_id=decision.id,
                    original_agent_proposal=agent_proposal, human_override_action=human_action,
                    override_reason="recipient not on approved list",
                )
            )
            # Two independent JSONB columns on the same row — confirm neither one's
            # structure leaks into or corrupts the other on write, and both come back
            # with exact type/order fidelity (lists staying lists, nested dicts intact).
            assert override.original_agent_proposal == agent_proposal
            assert override.human_override_action == human_action

            fetched = await repo.get_override_for_decision(decision.id)
            assert fetched is not None
            assert fetched.original_agent_proposal == agent_proposal
            assert fetched.human_override_action == human_action
    finally:
        await engine.dispose()


async def test_list_pending_expired_matches_only_intended_rows(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyHumanOversightRepository(session)
            now = datetime.now(UTC)
            past = now - timedelta(hours=1)
            future = now + timedelta(hours=1)

            # Expired + pending, matching tenant -> should be returned.
            expired_pending = await repo.create_request(
                OversightRequestRecord(
                    id=new_id(), tenant_id="tenant-a", requesting_module="m", requesting_ref="r1",
                    expires_at=past,
                )
            )
            # Expired + claimed, matching tenant -> should also be returned.
            expired_claimed = await repo.create_request(
                OversightRequestRecord(
                    id=new_id(), tenant_id="tenant-a", requesting_module="m", requesting_ref="r2",
                    expires_at=past, status=RequestStatus.CLAIMED, claimed_by="reviewer@x",
                )
            )
            # Not expired yet, matching tenant -> must NOT be returned.
            not_expired = await repo.create_request(
                OversightRequestRecord(
                    id=new_id(), tenant_id="tenant-a", requesting_module="m", requesting_ref="r3",
                    expires_at=future,
                )
            )
            # Expired but already decided, matching tenant -> must NOT be returned.
            expired_decided = await repo.create_request(
                OversightRequestRecord(
                    id=new_id(), tenant_id="tenant-a", requesting_module="m", requesting_ref="r4",
                    expires_at=past, status=RequestStatus.DECIDED,
                )
            )
            # Expired + pending, but a different tenant -> must NOT be returned.
            other_tenant = await repo.create_request(
                OversightRequestRecord(
                    id=new_id(), tenant_id="tenant-b", requesting_module="m", requesting_ref="r5",
                    expires_at=past,
                )
            )

            results = await repo.list_pending_expired("tenant-a", now)
            result_ids = {r.id for r in results}

            # A real multi-row WHERE with three predicates (tenant, status IN (...),
            # expires_at <= as_of) hitting exactly the intended rows and no others —
            # the kind of thing that's easy to get subtly wrong (e.g. off-by-one on
            # a timezone-naive comparison) and where SQLite's looser type affinity can
            # mask bugs that Postgres's strict `timestamptz` comparison won't.
            assert result_ids == {expired_pending.id, expired_claimed.id}
            assert not_expired.id not in result_ids
            assert expired_decided.id not in result_ids
            assert other_tenant.id not in result_ids
    finally:
        await engine.dispose()
