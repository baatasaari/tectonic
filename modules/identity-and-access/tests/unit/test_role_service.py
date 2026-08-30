"""Tests for core/role_service.py -- create/get/list."""
from __future__ import annotations

import pytest

from identity_and_access.core.domain import RoleNotFoundError


async def test_create_and_get_round_trip(harness):
    role = await harness.role_service.create(name="reader", scopes=["cards:read"], description="Read-only")

    assert role.scopes == ["cards:read"]

    fetched = await harness.role_service.get("reader")
    assert fetched.name == "reader"


async def test_get_raises_when_missing(harness):
    with pytest.raises(RoleNotFoundError):
        await harness.role_service.get("does-not-exist")


async def test_list_returns_all_roles(harness):
    await harness.role_service.create(name="reader", scopes=["cards:read"])
    await harness.role_service.create(name="writer", scopes=["cards:read", "cards:write"])

    roles, total = await harness.role_service.list()

    assert total == 2
    assert {r.name for r in roles} == {"reader", "writer"}
