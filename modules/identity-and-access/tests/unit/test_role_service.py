"""Tests for core/role_service.py -- create/get/list, now tenant-scoped
(IAM v2 foundation)."""
from __future__ import annotations

import pytest

from identity_and_access.core.domain import (
    PLATFORM_TENANT_ID,
    RoleAlreadyExistsError,
    RoleNotFoundError,
)


async def test_create_and_get_round_trip(harness):
    role = await harness.role_service.create(
        tenant_id="acme", name="reader", scopes=["cards:read"], description="Read-only",
    )

    assert role.scopes == ["cards:read"]
    assert role.tenant_id == "acme"

    fetched = await harness.role_service.get(tenant_id="acme", name="reader")
    assert fetched.name == "reader"


async def test_get_raises_when_missing(harness):
    with pytest.raises(RoleNotFoundError):
        await harness.role_service.get(tenant_id="acme", name="does-not-exist")


async def test_list_returns_only_the_given_tenants_roles(harness):
    await harness.role_service.create(tenant_id="acme", name="reader", scopes=["cards:read"])
    await harness.role_service.create(tenant_id="acme", name="writer", scopes=["cards:read", "cards:write"])
    await harness.role_service.create(tenant_id="globex", name="reader", scopes=["cards:read"])

    roles, total = await harness.role_service.list(tenant_id="acme")

    assert total == 2
    assert {r.name for r in roles} == {"reader", "writer"}
    assert all(r.tenant_id == "acme" for r in roles)


async def test_two_tenants_can_each_own_a_role_with_the_same_name(harness):
    """The actual bug this fixes: roles.name used to be the sole,
    platform-global primary key -- a second tenant creating a role
    called "admin" would fail outright once any other tenant already
    had one. Each tenant's "admin" is now independently scoped, and can
    carry entirely different scopes."""
    acme_admin = await harness.role_service.create(tenant_id="acme", name="admin", scopes=["cards:admin"])
    globex_admin = await harness.role_service.create(tenant_id="globex", name="admin", scopes=["cards:read"])

    assert acme_admin.id != globex_admin.id
    assert (await harness.role_service.get(tenant_id="acme", name="admin")).scopes == ["cards:admin"]
    assert (await harness.role_service.get(tenant_id="globex", name="admin")).scopes == ["cards:read"]


async def test_creating_a_duplicate_role_name_for_the_same_tenant_is_rejected(harness):
    await harness.role_service.create(tenant_id="acme", name="reader", scopes=["cards:read"])

    with pytest.raises(RoleAlreadyExistsError):
        await harness.role_service.create(tenant_id="acme", name="reader", scopes=["cards:read"])


async def test_a_tenant_without_its_own_role_falls_back_to_the_platform_wide_default(harness):
    await harness.role_service.create(tenant_id=PLATFORM_TENANT_ID, name="viewer", scopes=["cards:read"])

    fetched = await harness.role_service.get(tenant_id="acme", name="viewer")

    assert fetched.tenant_id == PLATFORM_TENANT_ID
    assert fetched.scopes == ["cards:read"]


async def test_a_tenants_own_role_shadows_the_platform_wide_default_of_the_same_name(harness):
    await harness.role_service.create(tenant_id=PLATFORM_TENANT_ID, name="admin", scopes=["cards:read"])
    await harness.role_service.create(tenant_id="acme", name="admin", scopes=["cards:admin", "cards:delete"])

    fetched = await harness.role_service.get(tenant_id="acme", name="admin")

    assert fetched.tenant_id == "acme"
    assert fetched.scopes == ["cards:admin", "cards:delete"]
