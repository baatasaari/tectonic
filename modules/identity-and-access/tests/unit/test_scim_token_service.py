"""Tests for core/scim_token_service.py -- show-once cleartext tokens,
SHA-256 stored, tenant-scoped verification."""
from __future__ import annotations

import pytest

from identity_and_access.core.domain import ScimTokenInvalidError


async def test_create_returns_stored_record_and_cleartext(harness):
    stored, cleartext = await harness.scim_token_service.create(tenant_id="acme", name="Okta SCIM")

    assert stored.tenant_id == "acme"
    assert stored.revoked is False
    assert stored.token_hash != cleartext  # never stored in cleartext


async def test_authenticate_succeeds_with_the_correct_token_and_tenant(harness):
    _, cleartext = await harness.scim_token_service.create(tenant_id="acme", name="Okta SCIM")

    record = await harness.scim_token_service.authenticate(tenant_id="acme", cleartext_token=cleartext)
    assert record.tenant_id == "acme"


async def test_authenticate_rejects_an_unknown_token(harness):
    with pytest.raises(ScimTokenInvalidError):
        await harness.scim_token_service.authenticate(tenant_id="acme", cleartext_token="not-a-real-token")


async def test_authenticate_rejects_the_right_token_for_the_wrong_tenant(harness):
    _, cleartext = await harness.scim_token_service.create(tenant_id="acme", name="Okta SCIM")

    with pytest.raises(ScimTokenInvalidError):
        await harness.scim_token_service.authenticate(tenant_id="globex", cleartext_token=cleartext)


async def test_authenticate_rejects_a_revoked_token(harness):
    stored, cleartext = await harness.scim_token_service.create(tenant_id="acme", name="Okta SCIM")
    await harness.scim_token_service.revoke(stored.id)

    with pytest.raises(ScimTokenInvalidError):
        await harness.scim_token_service.authenticate(tenant_id="acme", cleartext_token=cleartext)


async def test_revoke_of_an_unknown_token_returns_none(harness):
    assert await harness.scim_token_service.revoke("does-not-exist") is None


async def test_list_filters_by_tenant(harness):
    await harness.scim_token_service.create(tenant_id="acme", name="a")
    await harness.scim_token_service.create(tenant_id="globex", name="b")

    tokens, total = await harness.scim_token_service.list(tenant_id="acme")
    assert total == 1
    assert tokens[0].tenant_id == "acme"
