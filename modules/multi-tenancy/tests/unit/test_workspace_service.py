"""Tests for core/workspace_service.py -- register/suspend/reactivate/
delete for the second level of the platform hierarchy, and that
registration validates the parent tenant actually exists.
"""
from __future__ import annotations

import pytest

from multi_tenancy.core.domain import (
    HierarchyStatus,
    InvalidTransitionError,
    TenantNotFoundError,
    WorkspaceNotFoundError,
)


async def test_register_starts_active(harness):
    tenant = await harness.tenant_registry_service.register(name="Acme Corp")

    ws = await harness.workspace_service.register(tenant_id=tenant.id, name="Production workflows")

    assert ws.status == HierarchyStatus.ACTIVE
    assert ws.tenant_id == tenant.id


async def test_register_raises_for_an_unknown_tenant(harness):
    with pytest.raises(TenantNotFoundError):
        await harness.workspace_service.register(tenant_id="does-not-exist", name="Production workflows")


async def test_register_emits_an_audit_event(harness):
    tenant = await harness.tenant_registry_service.register(name="Acme Corp")
    ws = await harness.workspace_service.register(tenant_id=tenant.id, name="Production workflows")

    events = [e for e in harness.auditability.events if e["event"] == "workspace_created"]
    assert len(events) == 1
    assert events[0] == {
        "event": "workspace_created", "workspace_id": ws.id, "tenant_id": tenant.id, "name": "Production workflows",
    }


async def test_get_raises_when_missing(harness):
    with pytest.raises(WorkspaceNotFoundError):
        await harness.workspace_service.get("does-not-exist")


async def test_suspend_then_reactivate(harness):
    tenant = await harness.tenant_registry_service.register(name="Acme Corp")
    ws = await harness.workspace_service.register(tenant_id=tenant.id, name="Production workflows")

    suspended = await harness.workspace_service.suspend(ws.id, reason="incident")
    assert suspended.status == HierarchyStatus.SUSPENDED

    reactivated = await harness.workspace_service.reactivate(ws.id)
    assert reactivated.status == HierarchyStatus.ACTIVE


async def test_delete_is_terminal(harness):
    tenant = await harness.tenant_registry_service.register(name="Acme Corp")
    ws = await harness.workspace_service.register(tenant_id=tenant.id, name="Production workflows")
    await harness.workspace_service.delete(ws.id)

    with pytest.raises(InvalidTransitionError):
        await harness.workspace_service.reactivate(ws.id)


async def test_list_filters_by_tenant_and_status(harness):
    tenant_a = await harness.tenant_registry_service.register(name="Acme Corp")
    tenant_b = await harness.tenant_registry_service.register(name="Globex Corp")
    ws_a = await harness.workspace_service.register(tenant_id=tenant_a.id, name="A workspace")
    await harness.workspace_service.register(tenant_id=tenant_b.id, name="B workspace")

    results, total = await harness.workspace_service.list(tenant_id=tenant_a.id)

    assert total == 1
    assert results[0].id == ws_a.id


async def test_suspend_cascades_to_its_own_environments(harness):
    """A workspace suspended directly (not via a tenant-level cascade --
    e.g. through the API's own /workspaces/{id}/suspend) still carries
    its Environments with it -- the same gap this ticket also closed at
    the tenant level."""
    tenant = await harness.tenant_registry_service.register(name="Acme Corp")
    ws = await harness.workspace_service.register(tenant_id=tenant.id, name="Production")
    env = await harness.environment_service.register(workspace_id=ws.id, name="prod-us")

    await harness.workspace_service.suspend(ws.id, reason="maintenance")

    reloaded = await harness.environment_service.get(env.id)
    assert reloaded.status == HierarchyStatus.SUSPENDED


async def test_delete_cascades_to_its_own_environments(harness):
    tenant = await harness.tenant_registry_service.register(name="Acme Corp")
    ws = await harness.workspace_service.register(tenant_id=tenant.id, name="Production")
    env = await harness.environment_service.register(workspace_id=ws.id, name="prod-us")

    await harness.workspace_service.delete(ws.id)

    reloaded = await harness.environment_service.get(env.id)
    assert reloaded.status == HierarchyStatus.DELETED


async def test_reactivate_does_not_cascade_to_environments(harness):
    tenant = await harness.tenant_registry_service.register(name="Acme Corp")
    ws = await harness.workspace_service.register(tenant_id=tenant.id, name="Production")
    env = await harness.environment_service.register(workspace_id=ws.id, name="prod-us")
    await harness.workspace_service.suspend(ws.id, reason="maintenance")

    await harness.workspace_service.reactivate(ws.id)

    reloaded = await harness.environment_service.get(env.id)
    assert reloaded.status == HierarchyStatus.SUSPENDED


async def test_cascade_environments_is_idempotent(harness):
    tenant = await harness.tenant_registry_service.register(name="Acme Corp")
    ws = await harness.workspace_service.register(tenant_id=tenant.id, name="Production")
    env = await harness.environment_service.register(workspace_id=ws.id, name="prod-us")
    await harness.workspace_service.suspend(ws.id, reason="maintenance")

    # A second, direct cascade call (simulating TenantRegistryService's own
    # unconditional call) must not raise even though the environment is already there.
    await harness.workspace_service.cascade_environments(ws.id, HierarchyStatus.SUSPENDED, reason="retry")

    reloaded = await harness.environment_service.get(env.id)
    assert reloaded.status == HierarchyStatus.SUSPENDED
