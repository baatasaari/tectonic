"""Tests for core/developer_account_service.py -- registration composes
real Identity and Access + real Multi-tenancy calls; revoke is a
one-way transition that gates the real peer first."""
from __future__ import annotations

import pytest

from sdk_and_developer_portal.core.domain import (
    DeveloperNotFoundError,
    DeveloperRevokedError,
    DeveloperStatus,
    InvalidTransitionError,
)
from sdk_and_developer_portal.core.fakes import StubIdentityAccessClient, StubMultiTenancyClient


async def test_register_composes_identity_access_and_multi_tenancy(harness_factory):
    identity_access = StubIdentityAccessClient()
    multi_tenancy = StubMultiTenancyClient()
    h = harness_factory(identity_access=identity_access, multi_tenancy=multi_tenancy)

    developer = await h.developer_service.register(name="Ada", email="ada@example.com")

    assert developer.status.value == "active"
    assert identity_access.registered[0]["name"] == "Ada"
    assert identity_access.registered[0]["type"] == "user"
    assert multi_tenancy.created[0]["tier"] == "sandbox"
    assert developer.identity_id == identity_access.registered[0]["id"]
    assert developer.tenant_id == multi_tenancy.created[0]["id"]


async def test_register_propagates_a_down_identity_access(harness_factory):
    h = harness_factory(identity_access=StubIdentityAccessClient(raise_on_register=True))

    with pytest.raises(RuntimeError):
        await h.developer_service.register(name="Ada", email="ada@example.com")


async def test_get_raises_not_found(harness):
    with pytest.raises(DeveloperNotFoundError):
        await harness.developer_service.get("does-not-exist")


async def test_revoke_calls_the_real_identity_access_revoke_first(harness_factory):
    identity_access = StubIdentityAccessClient()
    h = harness_factory(identity_access=identity_access)
    developer = await h.developer_service.register(name="Ada", email="ada@example.com")

    revoked = await h.developer_service.revoke(developer.id)

    assert revoked.status.value == "revoked"
    assert identity_access.revoked == [developer.identity_id]


async def test_revoke_is_one_way(harness_factory):
    h = harness_factory()
    developer = await h.developer_service.register(name="Ada", email="ada@example.com")
    await h.developer_service.revoke(developer.id)

    with pytest.raises(InvalidTransitionError):
        await h.developer_service.revoke(developer.id)


async def test_issue_sandbox_token_proxies_identity_access(harness):
    developer = await harness.developer_service.register(name="Ada", email="ada@example.com")

    issued = await harness.developer_service.issue_sandbox_token(developer.id, requested_scopes=["cards:read"])

    assert issued["granted_scopes"] == ["cards:read"]


async def test_issue_sandbox_token_for_a_revoked_developer_raises(harness):
    developer = await harness.developer_service.register(name="Ada", email="ada@example.com")
    await harness.developer_service.revoke(developer.id)

    with pytest.raises(DeveloperRevokedError):
        await harness.developer_service.issue_sandbox_token(developer.id)


async def test_list_filters_by_status(harness):
    active = await harness.developer_service.register(name="Ada", email="ada@example.com")
    revoked = await harness.developer_service.register(name="Bea", email="bea@example.com")
    await harness.developer_service.revoke(revoked.id)

    results, total = await harness.developer_service.list(status=DeveloperStatus.ACTIVE)

    assert total == 1
    assert results[0].id == active.id
