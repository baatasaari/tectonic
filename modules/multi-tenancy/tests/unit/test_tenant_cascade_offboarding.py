"""Tests for TenantRegistryService's cascading offboarding: suspend()/
delete() carry every descendant Workspace and Environment with them
(independent architecture assessment §3.1's canonical hierarchy),
idempotently and with real audit events for every cascaded transition,
not just the root tenant's own.
"""
from __future__ import annotations

from multi_tenancy.core.domain import HierarchyStatus, TenantStatus


async def _register_tenant_with_hierarchy(harness):
    tenant = await harness.tenant_registry_service.register(name="Acme Corp")
    workspace = await harness.workspace_service.register(tenant_id=tenant.id, name="Production")
    environment = await harness.environment_service.register(workspace_id=workspace.id, name="prod-us")
    return tenant, workspace, environment


async def test_suspend_cascades_to_workspace_and_environment(harness):
    tenant, workspace, environment = await _register_tenant_with_hierarchy(harness)

    await harness.tenant_registry_service.suspend(tenant.id, reason="non-payment")

    reloaded_workspace = await harness.workspace_service.get(workspace.id)
    reloaded_environment = await harness.environment_service.get(environment.id)
    assert reloaded_workspace.status == HierarchyStatus.SUSPENDED
    assert reloaded_environment.status == HierarchyStatus.SUSPENDED


async def test_delete_cascades_to_workspace_and_environment(harness):
    tenant, workspace, environment = await _register_tenant_with_hierarchy(harness)

    await harness.tenant_registry_service.delete(tenant.id)

    reloaded_workspace = await harness.workspace_service.get(workspace.id)
    reloaded_environment = await harness.environment_service.get(environment.id)
    assert reloaded_workspace.status == HierarchyStatus.DELETED
    assert reloaded_environment.status == HierarchyStatus.DELETED


async def test_cascade_emits_audit_events_for_every_descendant(harness):
    tenant, workspace, environment = await _register_tenant_with_hierarchy(harness)
    harness.auditability.events.clear()

    await harness.tenant_registry_service.suspend(tenant.id, reason="non-payment")

    tenant_events = [e for e in harness.auditability.events if e["event"] == "tenant_status_changed"]
    workspace_events = [e for e in harness.auditability.events if e["event"] == "workspace_status_changed"]
    environment_events = [e for e in harness.auditability.events if e["event"] == "environment_status_changed"]
    assert len(tenant_events) == 1
    assert len(workspace_events) == 1
    assert workspace_events[0]["workspace_id"] == workspace.id
    assert workspace_events[0]["to_status"] == "suspended"
    assert len(environment_events) == 1
    assert environment_events[0]["environment_id"] == environment.id
    assert environment_events[0]["to_status"] == "suspended"


async def test_reactivate_does_not_cascade(harness):
    """A workspace/environment an operator suspended independently of
    the tenant must not silently reactivate just because the tenant
    did -- only suspend()/delete() cascade."""
    tenant, workspace, environment = await _register_tenant_with_hierarchy(harness)
    await harness.tenant_registry_service.suspend(tenant.id, reason="non-payment")

    await harness.tenant_registry_service.reactivate(tenant.id)

    reloaded_workspace = await harness.workspace_service.get(workspace.id)
    reloaded_environment = await harness.environment_service.get(environment.id)
    assert reloaded_workspace.status == HierarchyStatus.SUSPENDED
    assert reloaded_environment.status == HierarchyStatus.SUSPENDED


async def test_suspend_skips_an_already_deleted_workspace_without_raising(harness):
    """DELETED is terminal for HierarchyStatus -- a workspace already
    deleted independently of its tenant must be silently skipped by the
    cascade, not raise InvalidTransitionError and abort the whole
    suspend()."""
    tenant, workspace, _environment = await _register_tenant_with_hierarchy(harness)
    await harness.workspace_service.delete(workspace.id)

    suspended = await harness.tenant_registry_service.suspend(tenant.id, reason="non-payment")

    assert suspended.status == TenantStatus.SUSPENDED
    reloaded_workspace = await harness.workspace_service.get(workspace.id)
    assert reloaded_workspace.status == HierarchyStatus.DELETED  # untouched, not re-transitioned


async def test_cascade_is_idempotent_under_a_re_run(harness):
    """Simulates re-invoking suspend() after a partial-failure retry:
    the first call already cascaded everything, so a second call must
    converge (no InvalidTransitionError) rather than fail because the
    children are no longer ACTIVE."""
    tenant, workspace, environment = await _register_tenant_with_hierarchy(harness)
    await harness.tenant_registry_service.suspend(tenant.id, reason="non-payment")

    # The tenant itself is already SUSPENDED, so a second suspend() would raise at the
    # tenant level first -- exercise the cascade's own idempotency directly instead,
    # the same way a retried background worker might re-run just the cascade step.
    await harness.tenant_registry_service._cascade(tenant.id, HierarchyStatus.SUSPENDED, reason="retry")

    reloaded_workspace = await harness.workspace_service.get(workspace.id)
    reloaded_environment = await harness.environment_service.get(environment.id)
    assert reloaded_workspace.status == HierarchyStatus.SUSPENDED
    assert reloaded_environment.status == HierarchyStatus.SUSPENDED
    # No duplicate status-changed events from the second, no-op cascade pass.
    workspace_events = [e for e in harness.auditability.events if e["event"] == "workspace_status_changed"]
    assert len(workspace_events) == 1


async def test_cascade_handles_multiple_workspaces_and_environments(harness):
    tenant = await harness.tenant_registry_service.register(name="Acme Corp")
    ws1 = await harness.workspace_service.register(tenant_id=tenant.id, name="Production")
    ws2 = await harness.workspace_service.register(tenant_id=tenant.id, name="Staging")
    env1 = await harness.environment_service.register(workspace_id=ws1.id, name="prod-us")
    env2 = await harness.environment_service.register(workspace_id=ws1.id, name="prod-eu")
    env3 = await harness.environment_service.register(workspace_id=ws2.id, name="staging")

    await harness.tenant_registry_service.delete(tenant.id)

    for workspace_id in (ws1.id, ws2.id):
        reloaded = await harness.workspace_service.get(workspace_id)
        assert reloaded.status == HierarchyStatus.DELETED
    for environment_id in (env1.id, env2.id, env3.id):
        reloaded = await harness.environment_service.get(environment_id)
        assert reloaded.status == HierarchyStatus.DELETED


async def test_cascade_pages_through_more_workspaces_than_one_page(harness, monkeypatch):
    monkeypatch.setattr(
        "multi_tenancy.core.tenant_registry_service._CASCADE_PAGE_SIZE", 2,
    )
    tenant = await harness.tenant_registry_service.register(name="Acme Corp")
    workspaces = [
        await harness.workspace_service.register(tenant_id=tenant.id, name=f"ws-{i}") for i in range(5)
    ]

    await harness.tenant_registry_service.delete(tenant.id)

    for workspace in workspaces:
        reloaded = await harness.workspace_service.get(workspace.id)
        assert reloaded.status == HierarchyStatus.DELETED


async def test_suspending_a_tenant_with_no_workspaces_emits_only_the_tenant_event(harness):
    tenant = await harness.tenant_registry_service.register(name="Acme Corp")
    harness.auditability.events.clear()

    await harness.tenant_registry_service.suspend(tenant.id, reason="non-payment")

    assert [e["event"] for e in harness.auditability.events] == ["tenant_status_changed"]
