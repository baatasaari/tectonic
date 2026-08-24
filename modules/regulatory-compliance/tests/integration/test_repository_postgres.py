"""Integration tier (LLD §4 testing plan): the SQLAlchemy repository
against a real Postgres — not part of the default unit-test run. See
`conftest.py` for how the Postgres instance is obtained.

Specifically exercises what SQLite's unit-tier tests can't: real JSONB
list round-tripping (`clause_references`), real UUID primary keys, and a
multi-row upsert-style query (`deprecate_control_mappings`) against
genuine Postgres semantics.
"""
from __future__ import annotations

import os

import pytest
from alembic.config import Config as AlembicConfig
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from alembic import command
from regulatory_compliance.core.domain import (
    ControlMappingRecord,
    EvidencePackRecord,
    EvidencePackStatus,
    FrameworkProfileRecord,
    new_id,
)
from regulatory_compliance.db.repository import SQLAlchemyRegulatoryComplianceRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def migrated_url(postgres_url):
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", postgres_url)
    os.environ["REGULATORY_COMPLIANCE_DATABASE_URL"] = postgres_url
    command.upgrade(alembic_cfg, "head")
    return postgres_url


async def test_control_mapping_clause_references_round_trip_as_real_jsonb(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyRegulatoryComplianceRepository(session)
            record = ControlMappingRecord(
                id=new_id(), control_name="human_oversight", framework_name="gdpr", framework_version="2016",
                clause_references=["Art.22", "Art.5(1)(c)"], mapping_rationale="test",
            )
            created = await repo.upsert_control_mapping(record)
            assert created.clause_references == ["Art.22", "Art.5(1)(c)"]

            fetched = await repo.list_control_mappings(control_name="human_oversight", framework_name="gdpr")
            assert len(fetched) == 1
            # A real JSONB round trip preserves list order and element types — this is
            # exactly the kind of thing SQLite's JSON-as-TEXT variant can silently get
            # away with getting wrong that Postgres's native JSONB type won't.
            assert fetched[0].clause_references == ["Art.22", "Art.5(1)(c)"]
    finally:
        await engine.dispose()


async def test_deprecate_control_mappings_updates_only_matching_rows(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyRegulatoryComplianceRepository(session)
            await repo.upsert_control_mapping(
                ControlMappingRecord(
                    id=new_id(), control_name="audit_logging", framework_name="eu_ai_act", framework_version="2024",
                    clause_references=["Art.12"], mapping_rationale="v2024",
                )
            )
            await repo.upsert_control_mapping(
                ControlMappingRecord(
                    id=new_id(), control_name="audit_logging", framework_name="eu_ai_act", framework_version="2025",
                    clause_references=["Art.12a"], mapping_rationale="v2025",
                )
            )

            count = await repo.deprecate_control_mappings("audit_logging", "eu_ai_act", "2025")

            assert count == 1
            mappings = await repo.list_control_mappings(control_name="audit_logging", framework_name="eu_ai_act")
            deprecated = {m.framework_version: m.deprecated for m in mappings}
            assert deprecated == {"2024": True, "2025": False}
    finally:
        await engine.dispose()


async def test_framework_profile_and_evidence_pack_round_trip_with_real_uuid_pk(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyRegulatoryComplianceRepository(session)
            profile = await repo.create_framework_profile(
                FrameworkProfileRecord(id=new_id(), tenant_id="acme", framework_name="gdpr", version="2016")
            )
            # a real UUID (asyncpg returns/accepts a genuine UUID type; SQLite's CHAR(36)
            # variant just stores it as a plain string) — confirm it round-trips as a
            # fetchable primary key, not just a string that happens to look like one.
            fetched = await repo.get_framework_profile("acme", "gdpr")
            assert fetched is not None
            assert fetched.id == profile.id

            pack = await repo.create_evidence_pack(
                EvidencePackRecord(
                    id=new_id(), tenant_id="acme", framework_name="gdpr", status=EvidencePackStatus.GENERATING,
                )
            )
            pack.status = EvidencePackStatus.COMPLETED
            pack.coverage_percentage = 87.5
            pack.document_ref = "evidence-packs/x.pdf"
            updated = await repo.update_evidence_pack(pack)
            assert updated.status == EvidencePackStatus.COMPLETED
            assert updated.coverage_percentage == 87.5
    finally:
        await engine.dispose()
