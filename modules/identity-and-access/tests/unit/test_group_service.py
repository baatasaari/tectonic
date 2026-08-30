"""Tests for core/group_service.py -- CRUD plus the two live-recompute
paths (set_default_role_names, set_members) that keep an identity's
federated_role_names in sync with group state without needing a login
event."""
from __future__ import annotations

import pytest

from identity_and_access.core.domain import GroupNotFoundError


async def test_get_raises_when_missing(harness):
    with pytest.raises(GroupNotFoundError):
        await harness.group_service.get("does-not-exist")


async def test_set_members_recomputes_federated_role_names_for_added_members(harness):
    await harness.role_service.create(name="approver", scopes=["cards:approve"])
    group = await harness.group_service.register(
        tenant_id="acme", provider_id="scim", external_id="g1", name="Approvers", default_role_names=["approver"],
    )
    identity = await harness.identity_registry_service.register(tenant_id="acme", name="alice")
    assert identity.federated_role_names == []

    await harness.group_service.set_members(group.id, [identity.id])

    updated = await harness.identity_registry_service.get(identity.id)
    assert updated.federated_role_names == ["approver"]


async def test_set_members_recomputes_for_removed_members_too(harness):
    await harness.role_service.create(name="approver", scopes=["cards:approve"])
    group = await harness.group_service.register(
        tenant_id="acme", provider_id="scim", external_id="g1", name="Approvers", default_role_names=["approver"],
    )
    identity = await harness.identity_registry_service.register(tenant_id="acme", name="alice")
    await harness.group_service.set_members(group.id, [identity.id])

    await harness.group_service.set_members(group.id, [])

    updated = await harness.identity_registry_service.get(identity.id)
    assert updated.federated_role_names == []


async def test_an_identity_in_two_groups_gets_the_union_of_both(harness):
    await harness.role_service.create(name="approver", scopes=["cards:approve"])
    await harness.role_service.create(name="auditor", scopes=["cards:audit"])
    identity = await harness.identity_registry_service.register(tenant_id="acme", name="alice")
    group_a = await harness.group_service.register(
        tenant_id="acme", provider_id="scim", external_id="g1", name="Approvers", default_role_names=["approver"],
    )
    group_b = await harness.group_service.register(
        tenant_id="acme", provider_id="scim", external_id="g2", name="Auditors", default_role_names=["auditor"],
    )

    await harness.group_service.set_members(group_a.id, [identity.id])
    await harness.group_service.set_members(group_b.id, [identity.id])

    updated = await harness.identity_registry_service.get(identity.id)
    assert updated.federated_role_names == ["approver", "auditor"]


async def test_set_default_role_names_recomputes_for_existing_members(harness):
    await harness.role_service.create(name="approver", scopes=["cards:approve"])
    identity = await harness.identity_registry_service.register(tenant_id="acme", name="alice")
    group = await harness.group_service.register(
        tenant_id="acme", provider_id="scim", external_id="g1", name="Approvers",
    )
    await harness.group_service.set_members(group.id, [identity.id])
    assert (await harness.identity_registry_service.get(identity.id)).federated_role_names == []

    await harness.group_service.set_default_role_names(group.id, ["approver"])

    updated = await harness.identity_registry_service.get(identity.id)
    assert updated.federated_role_names == ["approver"]
