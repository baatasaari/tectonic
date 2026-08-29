"""Tests for core/token_service.py -- issues a scoped token narrowed to
`requested ∩ granted`, never more than an identity's roles actually
hold."""
from __future__ import annotations

import pytest

from identity_and_access.core.domain import IdentityNotActiveError, IdentityNotFoundError


async def test_issue_raises_when_identity_missing(harness):
    with pytest.raises(IdentityNotFoundError):
        await harness.token_service.issue(identity_id="does-not-exist")


async def test_issue_raises_when_identity_is_revoked(harness):
    identity = await harness.identity_registry_service.register(tenant_id="acme", name="agent-1")
    await harness.identity_registry_service.revoke(identity.id)

    with pytest.raises(IdentityNotActiveError):
        await harness.token_service.issue(identity_id=identity.id)


async def test_issue_with_no_requested_scopes_grants_everything_the_roles_hold(harness):
    await harness.role_service.create(name="reader", scopes=["cards:read"])
    await harness.role_service.create(name="writer", scopes=["cards:write"])
    identity = await harness.identity_registry_service.register(
        tenant_id="acme", name="agent-1", role_names=["reader", "writer"],
    )

    issued = await harness.token_service.issue(identity_id=identity.id)

    assert issued.granted_scopes == ["cards:read", "cards:write"]


async def test_issue_narrows_to_the_intersection_of_requested_and_granted(harness):
    await harness.role_service.create(name="reader", scopes=["cards:read"])
    identity = await harness.identity_registry_service.register(
        tenant_id="acme", name="agent-1", role_names=["reader"],
    )

    # Requesting a scope the identity's roles don't actually hold must never grant it.
    issued = await harness.token_service.issue(
        identity_id=identity.id, requested_scopes=["cards:read", "cards:delete"],
    )

    assert issued.granted_scopes == ["cards:read"]


async def test_issue_with_a_fully_unheld_requested_scope_grants_nothing(harness):
    await harness.role_service.create(name="reader", scopes=["cards:read"])
    identity = await harness.identity_registry_service.register(
        tenant_id="acme", name="agent-1", role_names=["reader"],
    )

    issued = await harness.token_service.issue(identity_id=identity.id, requested_scopes=["cards:delete"])

    assert issued.granted_scopes == []


async def test_issue_unions_role_names_and_federated_role_names(harness):
    """A federated login must never take away a manually-granted role, and a
    manually-granted role must never be required just to keep IdP-driven access
    working -- see core/token_service.py's own comment on this union."""
    await harness.role_service.create(name="reader", scopes=["cards:read"])
    await harness.role_service.create(name="approver", scopes=["cards:approve"])
    identity = await harness.identity_registry_service.register(
        tenant_id="acme", name="agent-1", role_names=["reader"],
    )
    identity.federated_role_names = ["approver"]
    await harness.repository.update_identity(identity)

    issued = await harness.token_service.issue(identity_id=identity.id)

    assert issued.granted_scopes == ["cards:approve", "cards:read"]


async def test_issued_token_verifies_with_the_signer(harness):
    await harness.role_service.create(name="reader", scopes=["cards:read"])
    identity = await harness.identity_registry_service.register(
        tenant_id="acme", name="agent-1", role_names=["reader"],
    )

    issued = await harness.token_service.issue(identity_id=identity.id)

    claims = harness.signer.verify(issued.token)
    assert claims["sub"] == identity.id
    assert claims["scopes"] == ["cards:read"]
