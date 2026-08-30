"""Integration tier: `POST /v1/guardrails/check` against a real Postgres,
for a tenant that has never created a policy profile of its own -- ticket
#82's own real-live-stack verification surfaced this as a genuine 500,
invisible under every prior stubbed/unit test (which never exercises the
real route + a real UUID-typed column together): `_default_profile`'s
in-memory fallback profile used the literal string "default" as its
`id`, and `create_intervention_log` writes that value straight into a
real UUID column -- a fine value for SQLite's untyped CHAR(36) column,
a `DataError` against genuine Postgres UUID semantics. See
`routes_guardrails.py`'s own updated docstring on `_default_profile` for
the fix.
"""
from __future__ import annotations

import os

import pytest
from alembic.config import Config as AlembicConfig
from fastapi.testclient import TestClient

from alembic import command

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def migrated_url(postgres_url):
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", postgres_url)
    os.environ["GUARDRAILS_DATABASE_URL"] = postgres_url
    command.upgrade(alembic_cfg, "head")
    return postgres_url


async def test_check_with_no_policy_profile_id_and_no_existing_tenant_profile_does_not_500(migrated_url):
    from guardrails.main import create_app
    from guardrails.security.jwt_auth import mint_service_token

    app = create_app()
    with TestClient(app) as client:
        settings = app.state.settings
        token = mint_service_token(
            issuer="test", audience=settings.service_name, shared_secret=settings.jwt_shared_secret,
        )
        resp = client.post(
            "/v1/guardrails/check",
            json={"text": "hello there", "stage": "input"},
            headers={"Authorization": f"Bearer {token}", "X-Tenant-Id": "a-brand-new-tenant-no-profile-yet"},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["decision"] in ("allow", "block", "redact")
