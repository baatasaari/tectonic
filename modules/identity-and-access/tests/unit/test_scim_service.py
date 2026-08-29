"""Tests for core/scim_service.py -- SCIM User/Group lifecycle mapped
onto IdentityRecord/GroupRecord, the bounded filter/PATCH grammar, and
tenant isolation."""
from __future__ import annotations

import pytest

from identity_and_access.core.domain import (
    GroupNotFoundError,
    IdentityNotFoundError,
    IdentityStatus,
    ScimConflictError,
)
from identity_and_access.core.scim_service import parse_username_filter


def test_parse_username_filter_extracts_the_quoted_value():
    assert parse_username_filter('userName eq "alice@acme.com"') == "alice@acme.com"


def test_parse_username_filter_is_case_insensitive_on_the_operator():
    assert parse_username_filter('userName EQ "alice@acme.com"') == "alice@acme.com"


def test_parse_username_filter_returns_none_for_unsupported_shapes():
    assert parse_username_filter('emails.value eq "alice@acme.com"') is None
    assert parse_username_filter(None) is None


async def test_create_user_and_get(harness):
    identity = await harness.scim_user_service.create(tenant_id="acme", user_name="alice@acme.com", display_name="Alice")

    fetched = await harness.scim_user_service.get(tenant_id="acme", identity_id=identity.id)
    assert fetched.email == "alice@acme.com"
    assert fetched.status == IdentityStatus.ACTIVE


async def test_create_user_rejects_a_duplicate_username_in_the_same_tenant(harness):
    await harness.scim_user_service.create(tenant_id="acme", user_name="alice@acme.com", display_name="Alice")

    with pytest.raises(ScimConflictError):
        await harness.scim_user_service.create(tenant_id="acme", user_name="alice@acme.com", display_name="Alice 2")


async def test_get_scopes_to_tenant(harness):
    identity = await harness.scim_user_service.create(tenant_id="acme", user_name="alice@acme.com", display_name="Alice")

    with pytest.raises(IdentityNotFoundError):
        await harness.scim_user_service.get(tenant_id="globex", identity_id=identity.id)


async def test_list_filters_by_username(harness):
    await harness.scim_user_service.create(tenant_id="acme", user_name="alice@acme.com", display_name="Alice")
    await harness.scim_user_service.create(tenant_id="acme", user_name="bob@acme.com", display_name="Bob")

    users, total = await harness.scim_user_service.list(tenant_id="acme", user_name="alice@acme.com")
    assert total == 1
    assert users[0].email == "alice@acme.com"


async def test_patch_active_false_deactivates(harness):
    identity = await harness.scim_user_service.create(tenant_id="acme", user_name="alice@acme.com", display_name="Alice")

    updated = await harness.scim_user_service.patch(
        tenant_id="acme", identity_id=identity.id, operations=[{"op": "replace", "path": "active", "value": False}],
    )

    assert updated.status == IdentityStatus.REVOKED


async def test_deactivate_is_a_soft_delete_not_a_hard_one(harness):
    identity = await harness.scim_user_service.create(tenant_id="acme", user_name="alice@acme.com", display_name="Alice")

    await harness.scim_user_service.deactivate(tenant_id="acme", identity_id=identity.id)

    fetched = await harness.scim_user_service.get(tenant_id="acme", identity_id=identity.id)
    assert fetched.status == IdentityStatus.REVOKED


async def test_replace_updates_username_and_display_name(harness):
    identity = await harness.scim_user_service.create(tenant_id="acme", user_name="alice@acme.com", display_name="Alice")

    updated = await harness.scim_user_service.replace(
        tenant_id="acme", identity_id=identity.id, user_name="alice.smith@acme.com", display_name="Alice Smith",
        active=True,
    )

    assert updated.email == "alice.smith@acme.com"
    assert updated.name == "Alice Smith"


# -- Groups --

async def test_create_group_with_members(harness):
    user = await harness.scim_user_service.create(tenant_id="acme", user_name="alice@acme.com", display_name="Alice")

    group = await harness.scim_group_service.create(tenant_id="acme", display_name="Engineers", member_ids=[user.id])

    assert group.member_identity_ids == [user.id]
    assert group.provider_id == "scim"


async def test_group_get_scopes_to_tenant(harness):
    group = await harness.scim_group_service.create(tenant_id="acme", display_name="Engineers")

    with pytest.raises(GroupNotFoundError):
        await harness.scim_group_service.get(tenant_id="globex", group_id=group.id)


async def test_patch_add_members(harness):
    user = await harness.scim_user_service.create(tenant_id="acme", user_name="alice@acme.com", display_name="Alice")
    group = await harness.scim_group_service.create(tenant_id="acme", display_name="Engineers")

    updated = await harness.scim_group_service.patch(
        tenant_id="acme", group_id=group.id,
        operations=[{"op": "add", "path": "members", "value": [{"value": user.id}]}],
    )

    assert updated.member_identity_ids == [user.id]


async def test_patch_remove_a_single_member_by_value_filter(harness):
    user = await harness.scim_user_service.create(tenant_id="acme", user_name="alice@acme.com", display_name="Alice")
    group = await harness.scim_group_service.create(tenant_id="acme", display_name="Engineers", member_ids=[user.id])

    updated = await harness.scim_group_service.patch(
        tenant_id="acme", group_id=group.id,
        operations=[{"op": "remove", "path": f'members[value eq "{user.id}"]'}],
    )

    assert updated.member_identity_ids == []


async def test_patch_replace_members_replaces_the_whole_set(harness):
    user_a = await harness.scim_user_service.create(tenant_id="acme", user_name="a@acme.com", display_name="A")
    user_b = await harness.scim_user_service.create(tenant_id="acme", user_name="b@acme.com", display_name="B")
    group = await harness.scim_group_service.create(tenant_id="acme", display_name="Engineers", member_ids=[user_a.id])

    updated = await harness.scim_group_service.patch(
        tenant_id="acme", group_id=group.id,
        operations=[{"op": "replace", "path": "members", "value": [{"value": user_b.id}]}],
    )

    assert updated.member_identity_ids == [user_b.id]


async def test_group_membership_change_propagates_to_federated_role_names(harness):
    await harness.role_service.create(name="approver", scopes=["cards:approve"])
    user = await harness.scim_user_service.create(tenant_id="acme", user_name="alice@acme.com", display_name="Alice")
    group = await harness.scim_group_service.create(tenant_id="acme", display_name="Approvers")
    await harness.group_service.set_default_role_names(group.id, ["approver"])

    await harness.scim_group_service.patch(
        tenant_id="acme", group_id=group.id,
        operations=[{"op": "add", "path": "members", "value": [{"value": user.id}]}],
    )

    updated = await harness.identity_registry_service.get(user.id)
    assert updated.federated_role_names == ["approver"]


async def test_delete_group_clears_membership_and_downstream_roles(harness):
    await harness.role_service.create(name="approver", scopes=["cards:approve"])
    user = await harness.scim_user_service.create(tenant_id="acme", user_name="alice@acme.com", display_name="Alice")
    group = await harness.scim_group_service.create(tenant_id="acme", display_name="Approvers", member_ids=[user.id])
    await harness.group_service.set_default_role_names(group.id, ["approver"])
    assert (await harness.identity_registry_service.get(user.id)).federated_role_names == ["approver"]

    await harness.scim_group_service.delete(tenant_id="acme", group_id=group.id)

    updated = await harness.identity_registry_service.get(user.id)
    assert updated.federated_role_names == []
