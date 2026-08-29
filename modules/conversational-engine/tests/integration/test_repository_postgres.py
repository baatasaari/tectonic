"""Integration tier (LLD §4 testing plan): the SQLAlchemy repository
against a real Postgres — not part of the default unit-test run. See
`conftest.py` for how the Postgres instance is obtained.

Specifically exercises what SQLite's unit-tier tests can't: a nested-dict
`guardrail_check_result` round-tripping through real JSONB on `Message`,
`PersonaConfig`'s `tone_settings` dict plus `allowed_topics`/`denied_topics`
lists round-tripping with exact type/order preservation, and a real UUID
primary key round trip on `ConversationSession`.
"""
from __future__ import annotations

import os

import pytest
from alembic.config import Config as AlembicConfig
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from alembic import command
from conversational_engine.core.domain import (
    Channel,
    ConversationSessionRecord,
    HandoffEventRecord,
    HandoffTriggerReason,
    MessageDirection,
    MessageRecord,
    new_id,
)
from conversational_engine.db import models
from conversational_engine.db.repository import SQLAlchemyConversationRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def migrated_url(postgres_url):
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", postgres_url)
    os.environ["CONVERSATIONAL_ENGINE_DATABASE_URL"] = postgres_url
    command.upgrade(alembic_cfg, "head")
    return postgres_url


async def test_message_guardrail_check_result_round_trips_nested_json(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyConversationRepository(session)
            created_session = await repo.create_session(
                ConversationSessionRecord(
                    id=new_id(), tenant_id="acme", channel=Channel.WEB, trace_id="trace-1",
                )
            )
            nested_result = {
                "blocked": False,
                "categories": ["self_harm", "violence"],
                "scores": {"self_harm": 0.02, "violence": 0.11},
            }
            appended = await repo.append_message(
                MessageRecord(
                    id=new_id(), session_id=created_session.id, direction=MessageDirection.OUTBOUND,
                    content="hello there", guardrail_check_result=nested_result,
                )
            )
            # A real JSONB round trip preserves nested dict/list structure and element
            # types exactly — this is exactly the kind of thing SQLite's JSON-as-TEXT
            # variant can silently get away with getting wrong.
            assert appended.guardrail_check_result == nested_result

            fetched = await repo.list_messages(created_session.id)
            assert len(fetched) == 1
            assert fetched[0].guardrail_check_result == nested_result
            assert fetched[0].guardrail_check_result["categories"] == ["self_harm", "violence"]
    finally:
        await engine.dispose()


async def test_persona_config_tone_settings_and_topics_round_trip_as_real_jsonb(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            # No create_persona_config exists on the repository (personas are seeded
            # data), so insert the row directly and exercise the real repository's
            # get_persona_config to prove the JSONB columns come back intact.
            persona_id = new_id()
            m = models.PersonaConfig(
                id=persona_id, tenant_id="acme", name="support",
                tone_settings={"formality": "casual", "emoji_ok": True},
                allowed_topics=["billing", "shipping"],
                denied_topics=["medical_advice"],
            )
            session.add(m)
            await session.commit()

            repo = SQLAlchemyConversationRepository(session)
            fetched = await repo.get_persona_config(persona_id, "acme")
            assert fetched is not None
            assert fetched.tone_settings == {"formality": "casual", "emoji_ok": True}
            # List order and element types survive a real JSONB round trip.
            assert fetched.allowed_topics == ["billing", "shipping"]
            assert fetched.denied_topics == ["medical_advice"]
    finally:
        await engine.dispose()


async def test_conversation_session_round_trips_real_uuid_pk(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyConversationRepository(session)
            created = await repo.create_session(
                ConversationSessionRecord(
                    id=new_id(), tenant_id="acme", channel=Channel.WHATSAPP, trace_id="trace-2",
                )
            )
            # asyncpg returns/accepts a genuine UUID type for the primary key; SQLite's
            # CHAR(36) variant just stores it as a plain string. Confirm it round-trips
            # as a fetchable primary key against real Postgres UUID semantics.
            fetched = await repo.get_session(created.id)
            assert fetched is not None
            assert fetched.id == created.id
            assert fetched.channel == Channel.WHATSAPP
    finally:
        await engine.dispose()


async def test_get_latest_handoff_event_returns_the_most_recent_one_for_the_right_session(migrated_url):
    """ticket #82: resume_from_workflow's own real-Postgres-backed lookup --
    a session can accumulate more than one handoff event over its lifetime
    (e.g. a manual handoff followed later by a workflow escalation), and
    the most recent one is the one that matters for resuming."""
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyConversationRepository(session)
            created = await repo.create_session(
                ConversationSessionRecord(id=new_id(), tenant_id="acme", channel=Channel.WEB, trace_id="trace-3")
            )
            other_session = await repo.create_session(
                ConversationSessionRecord(id=new_id(), tenant_id="acme", channel=Channel.WEB, trace_id="trace-4")
            )

            assert await repo.get_latest_handoff_event(created.id) is None

            await repo.create_handoff_event(
                HandoffEventRecord(
                    id=new_id(), session_id=created.id, trigger_reason=HandoffTriggerReason.EXPLICIT, target="human:t-1"
                )
            )
            await repo.create_handoff_event(
                HandoffEventRecord(
                    id=new_id(), session_id=other_session.id, trigger_reason=HandoffTriggerReason.EXPLICIT,
                    target="human:t-other",
                )
            )
            latest = HandoffEventRecord(
                id=new_id(), session_id=created.id, trigger_reason=HandoffTriggerReason.WORKFLOW_ESCALATION,
                target="workflow-instance:wf-1",
            )
            await repo.create_handoff_event(latest)

            fetched = await repo.get_latest_handoff_event(created.id)
            assert fetched is not None
            assert fetched.id == latest.id
            assert fetched.trigger_reason == HandoffTriggerReason.WORKFLOW_ESCALATION
            assert fetched.target == "workflow-instance:wf-1"
    finally:
        await engine.dispose()
