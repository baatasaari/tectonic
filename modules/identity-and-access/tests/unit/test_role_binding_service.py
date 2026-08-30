"""Tests for core/role_binding_service.py -- grant/revoke a single role on
an already-registered identity, and the durable RoleBindingRecord audit
trail each grant/revoke leaves behind (IAM v2 foundation)."""
from __future__ import annotations

import pytest

from identity_and_access.core.domain import (
    IdentityNotFoundError,
    RoleNotFoundError,
    RoleNotGrantedError,
)


async def test_grant_adds_the_role_and_writes_a_binding(harness):
    await harness.role_service.create(tenant_id="acme", name="reader", scopes=["cards:read"])
    identity = await harness.identity_registry_service.register(tenant_id="acme", name="agent-1")

    updated = await harness.role_binding_service.grant(
        identity_id=identity.id, role_name="reader", granted_by="operator-1",
    )

    assert updated.role_names == ["reader"]

    bindings, total = await harness.role_binding_service.list_bindings(identity_id=identity.id)
    assert total == 1
    assert bindings[0].role_name == "reader"
    assert bindings[0].granted_by == "operator-1"
    assert bindings[0].revoked_at is None


async def test_grant_raises_for_a_missing_identity(harness):
    await harness.role_service.create(tenant_id="acme", name="reader", scopes=["cards:read"])

    with pytest.raises(IdentityNotFoundError):
        await harness.role_binding_service.grant(identity_id="does-not-exist", role_name="reader")


async def test_grant_raises_for_an_unknown_role(harness):
    identity = await harness.identity_registry_service.register(tenant_id="acme", name="agent-1")

    with pytest.raises(RoleNotFoundError):
        await harness.role_binding_service.grant(identity_id=identity.id, role_name="does-not-exist")


async def test_grant_rejects_a_role_that_only_exists_for_a_different_tenant(harness):
    await harness.role_service.create(tenant_id="globex", name="reader", scopes=["cards:read"])
    identity = await harness.identity_registry_service.register(tenant_id="acme", name="agent-1")

    with pytest.raises(RoleNotFoundError):
        await harness.role_binding_service.grant(identity_id=identity.id, role_name="reader")


async def test_granting_an_already_held_role_is_idempotent_and_does_not_duplicate_the_binding(harness):
    await harness.role_service.create(tenant_id="acme", name="reader", scopes=["cards:read"])
    identity = await harness.identity_registry_service.register(
        tenant_id="acme", name="agent-1", role_names=["reader"],
    )

    updated = await harness.role_binding_service.grant(identity_id=identity.id, role_name="reader")

    assert updated.role_names == ["reader"]
    _bindings, total = await harness.role_binding_service.list_bindings(identity_id=identity.id)
    assert total == 0  # granted at registration time, not through this service -- no binding row for that


async def test_revoke_removes_the_role_and_marks_the_binding_revoked(harness):
    await harness.role_service.create(tenant_id="acme", name="reader", scopes=["cards:read"])
    identity = await harness.identity_registry_service.register(tenant_id="acme", name="agent-1")
    await harness.role_binding_service.grant(identity_id=identity.id, role_name="reader")

    updated = await harness.role_binding_service.revoke(identity_id=identity.id, role_name="reader")

    assert updated.role_names == []
    bindings, total = await harness.role_binding_service.list_bindings(identity_id=identity.id)
    assert total == 1  # same row, updated in place
    assert bindings[0].revoked_at is not None


async def test_revoke_raises_for_a_missing_identity(harness):
    with pytest.raises(IdentityNotFoundError):
        await harness.role_binding_service.revoke(identity_id="does-not-exist", role_name="reader")


async def test_revoke_raises_when_the_role_was_never_granted(harness):
    identity = await harness.identity_registry_service.register(tenant_id="acme", name="agent-1")

    with pytest.raises(RoleNotGrantedError):
        await harness.role_binding_service.revoke(identity_id=identity.id, role_name="reader")


async def test_grant_then_revoke_then_grant_again_produces_two_binding_rows(harness):
    """Re-granting after a revoke is a genuinely new grant event -- it must
    get its own row (with its own granted_at/granted_by), not resurrect
    the old, now-revoked one."""
    await harness.role_service.create(tenant_id="acme", name="reader", scopes=["cards:read"])
    identity = await harness.identity_registry_service.register(tenant_id="acme", name="agent-1")

    await harness.role_binding_service.grant(identity_id=identity.id, role_name="reader", granted_by="op-1")
    await harness.role_binding_service.revoke(identity_id=identity.id, role_name="reader")
    updated = await harness.role_binding_service.grant(identity_id=identity.id, role_name="reader", granted_by="op-2")

    assert updated.role_names == ["reader"]
    bindings, total = await harness.role_binding_service.list_bindings(identity_id=identity.id)
    assert total == 2
    active = [b for b in bindings if b.revoked_at is None]
    assert len(active) == 1
    assert active[0].granted_by == "op-2"
