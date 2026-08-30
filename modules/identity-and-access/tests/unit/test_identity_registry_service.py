"""Tests for core/identity_registry_service.py -- register/revoke/
reinstate and the identity lifecycle state machine."""
from __future__ import annotations

import pytest

from identity_and_access.core.domain import (
    IdentityNotFoundError,
    IdentityStatus,
    IdentityType,
    InvalidTransitionError,
    RoleNotFoundError,
)


async def test_register_starts_active(harness):
    identity = await harness.identity_registry_service.register(
        tenant_id="acme", name="claims-processor-agent", type=IdentityType.AGENT,
    )

    assert identity.status == IdentityStatus.ACTIVE
    assert identity.type == IdentityType.AGENT

    fetched = await harness.identity_registry_service.get(identity.id)
    assert fetched.id == identity.id


async def test_register_rejects_an_unknown_role(harness):
    with pytest.raises(RoleNotFoundError):
        await harness.identity_registry_service.register(
            tenant_id="acme", name="agent-1", role_names=["does-not-exist"],
        )


async def test_register_with_a_real_role(harness):
    await harness.role_service.create(name="reader", scopes=["cards:read"])

    identity = await harness.identity_registry_service.register(
        tenant_id="acme", name="agent-1", role_names=["reader"],
    )

    assert identity.role_names == ["reader"]


async def test_register_rejects_a_role_that_only_exists_for_a_different_tenant(harness):
    """The IAM v2 tenant-scoped-roles fix's own regression test: a role
    created for one tenant (not the platform-wide default) must not be
    assignable when registering an identity in a different tenant."""
    await harness.role_service.create(tenant_id="globex", name="reader", scopes=["cards:read"])

    with pytest.raises(RoleNotFoundError):
        await harness.identity_registry_service.register(
            tenant_id="acme", name="agent-1", role_names=["reader"],
        )


async def test_get_raises_when_missing(harness):
    with pytest.raises(IdentityNotFoundError):
        await harness.identity_registry_service.get("does-not-exist")


async def test_revoke_then_reinstate(harness):
    identity = await harness.identity_registry_service.register(tenant_id="acme", name="agent-1")

    revoked = await harness.identity_registry_service.revoke(identity.id)
    assert revoked.status == IdentityStatus.REVOKED

    reinstated = await harness.identity_registry_service.reinstate(identity.id)
    assert reinstated.status == IdentityStatus.ACTIVE


async def test_revoke_on_an_already_revoked_identity_is_illegal(harness):
    identity = await harness.identity_registry_service.register(tenant_id="acme", name="agent-1")
    await harness.identity_registry_service.revoke(identity.id)

    with pytest.raises(InvalidTransitionError):
        await harness.identity_registry_service.revoke(identity.id)


async def test_list_filters_by_tenant_and_status(harness):
    a = await harness.identity_registry_service.register(tenant_id="acme", name="active-agent")
    b = await harness.identity_registry_service.register(tenant_id="acme", name="revoked-agent")
    await harness.identity_registry_service.revoke(b.id)
    await harness.identity_registry_service.register(tenant_id="other", name="other-tenant-agent")

    active_only, total = await harness.identity_registry_service.list(tenant_id="acme", status=IdentityStatus.ACTIVE)

    assert total == 1
    assert active_only[0].id == a.id
