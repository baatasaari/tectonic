"""Integration tier for the OIDC/SAML federation + SCIM additions:
identity_providers/groups/scim_tokens tables, the new identities columns
(email/external_provider_id/external_subject/federated_role_names), and
the find-by-external-key lookups the JIT-provisioning and SCIM-auth
paths depend on -- unlike role_names/scopes, these are exercised for the
first time here, not just re-verified.
"""
from __future__ import annotations

import os

import pytest
from alembic.config import Config as AlembicConfig
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from alembic import command
from identity_and_access.core.domain import (
    GroupRecord,
    IdentityProviderRecord,
    IdentityProviderType,
    IdentityRecord,
    ScimTokenRecord,
    new_id,
)
from identity_and_access.db.repository import SQLAlchemyIdentityAccessRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def migrated_url(postgres_url):
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", postgres_url)
    os.environ["IDENTITY_ACCESS_DATABASE_URL"] = postgres_url
    command.upgrade(alembic_cfg, "head")
    return postgres_url


async def test_identity_federation_columns_round_trip(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyIdentityAccessRepository(session)
            provider_id = f"p-{new_id()[:8]}"
            subject = f"okta-user-{new_id()[:8]}"
            identity = await repo.create_identity(
                IdentityRecord(
                    id=new_id(), tenant_id="acme", name="Alice", email="alice@acme.com",
                    external_provider_id=provider_id, external_subject=subject,
                    federated_role_names=["approver", "auditor"],
                ),
            )

            fetched = await repo.get_identity(identity.id)
            assert fetched.email == "alice@acme.com"
            assert fetched.external_provider_id == provider_id
            assert fetched.external_subject == subject
            assert fetched.federated_role_names == ["approver", "auditor"]
    finally:
        await engine.dispose()


async def test_find_identity_by_external_subject_round_trips(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyIdentityAccessRepository(session)
            # Unique per test run -- this fixture's Postgres database is module-scoped
            # (shared across every test in this file), so a fixed subject would collide
            # with rows other tests in this module already inserted.
            provider_id = f"p-{new_id()[:8]}"
            subject = f"okta-user-{new_id()[:8]}"
            identity = await repo.create_identity(
                IdentityRecord(
                    id=new_id(), tenant_id="acme", name="Alice", external_provider_id=provider_id,
                    external_subject=subject,
                ),
            )

            found = await repo.find_identity_by_external_subject(
                tenant_id="acme", provider_id=provider_id, external_subject=subject,
            )
            assert found is not None
            assert found.id == identity.id

            missing = await repo.find_identity_by_external_subject(
                tenant_id="acme", provider_id=provider_id, external_subject="no-such-subject",
            )
            assert missing is None
    finally:
        await engine.dispose()


async def test_identity_provider_crud_round_trips(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyIdentityAccessRepository(session)
            created = await repo.create_identity_provider(
                IdentityProviderRecord(
                    id=new_id(), tenant_id="acme", name="Okta", provider_type=IdentityProviderType.OIDC,
                    issuer="https://acme.okta.com", client_id="client-1", jwks_uri="https://acme.okta.com/jwks",
                ),
            )

            fetched = await repo.get_identity_provider(created.id)
            assert fetched.issuer == "https://acme.okta.com"
            assert fetched.enabled is True

            fetched.enabled = False
            updated = await repo.update_identity_provider(fetched)
            assert updated.enabled is False

            providers, total = await repo.list_identity_providers(tenant_id="acme", limit=200)
            assert any(p.id == created.id for p in providers)
            assert total >= 1
    finally:
        await engine.dispose()


async def test_group_membership_and_default_role_names_round_trip(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyIdentityAccessRepository(session)
            member_id = new_id()
            created = await repo.create_group(
                GroupRecord(
                    id=new_id(), tenant_id="acme", provider_id="scim", external_id="g1", name="Engineers",
                    default_role_names=["writer"], member_identity_ids=[member_id],
                ),
            )

            fetched = await repo.get_group(created.id)
            assert fetched.default_role_names == ["writer"]
            assert fetched.member_identity_ids == [member_id]

            found = await repo.find_group_by_external_id(tenant_id="acme", provider_id="scim", external_id="g1")
            assert found is not None
            assert found.id == created.id

            fetched.member_identity_ids = []
            updated = await repo.update_group(fetched)
            assert updated.member_identity_ids == []
    finally:
        await engine.dispose()


async def test_scim_token_lookup_by_hash_and_revoke_round_trip(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyIdentityAccessRepository(session)
            token_hash = new_id().replace("-", "")
            created = await repo.create_scim_token(
                ScimTokenRecord(id=new_id(), tenant_id="acme", name="Okta SCIM", token_hash=token_hash),
            )

            found = await repo.get_scim_token_by_hash(token_hash)
            assert found is not None
            assert found.id == created.id
            assert found.revoked is False

            revoked = await repo.revoke_scim_token(created.id)
            assert revoked.revoked is True

            missing = await repo.get_scim_token_by_hash("not-a-real-hash")
            assert missing is None
    finally:
        await engine.dispose()
