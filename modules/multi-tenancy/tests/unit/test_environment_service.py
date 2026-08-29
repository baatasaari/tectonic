"""Tests for core/environment_service.py -- register/suspend/reactivate/
delete for the third level of the platform hierarchy, and that
registration validates the parent workspace actually exists.
"""
from __future__ import annotations

import pytest

from multi_tenancy.core.domain import (
    EnvironmentNotFoundError,
    HierarchyStatus,
    InvalidTransitionError,
    WorkspaceNotFoundError,
)


async def _make_workspace(harness):
    tenant = await harness.tenant_registry_service.register(name="Acme Corp")
    return await harness.workspace_service.register(tenant_id=tenant.id, name="Production workflows")


async def test_register_starts_active(harness):
    ws = await _make_workspace(harness)

    env = await harness.environment_service.register(workspace_id=ws.id, name="production", kind="production")

    assert env.status == HierarchyStatus.ACTIVE
    assert env.workspace_id == ws.id
    assert env.kind == "production"


async def test_register_defaults_kind_to_development(harness):
    ws = await _make_workspace(harness)

    env = await harness.environment_service.register(workspace_id=ws.id, name="dev")

    assert env.kind == "development"


async def test_register_raises_for_an_unknown_workspace(harness):
    with pytest.raises(WorkspaceNotFoundError):
        await harness.environment_service.register(workspace_id="does-not-exist", name="production")


async def test_register_emits_an_audit_event(harness):
    ws = await _make_workspace(harness)
    env = await harness.environment_service.register(workspace_id=ws.id, name="production", kind="production")

    events = [e for e in harness.auditability.events if e["event"] == "environment_created"]
    assert len(events) == 1
    assert events[0] == {
        "event": "environment_created", "environment_id": env.id, "workspace_id": ws.id,
        "name": "production", "kind": "production",
    }


async def test_get_raises_when_missing(harness):
    with pytest.raises(EnvironmentNotFoundError):
        await harness.environment_service.get("does-not-exist")


async def test_suspend_then_reactivate(harness):
    ws = await _make_workspace(harness)
    env = await harness.environment_service.register(workspace_id=ws.id, name="production")

    suspended = await harness.environment_service.suspend(env.id, reason="incident", expected_version=1)
    assert suspended.status == HierarchyStatus.SUSPENDED

    reactivated = await harness.environment_service.reactivate(env.id, expected_version=2)
    assert reactivated.status == HierarchyStatus.ACTIVE


async def test_delete_is_terminal(harness):
    ws = await _make_workspace(harness)
    env = await harness.environment_service.register(workspace_id=ws.id, name="production")
    await harness.environment_service.delete(env.id, expected_version=1)

    with pytest.raises(InvalidTransitionError):
        await harness.environment_service.reactivate(env.id, expected_version=2)


async def test_list_filters_by_workspace_and_status(harness):
    ws_a = await _make_workspace(harness)
    ws_b = await _make_workspace(harness)
    env_a = await harness.environment_service.register(workspace_id=ws_a.id, name="prod-a")
    await harness.environment_service.register(workspace_id=ws_b.id, name="prod-b")

    results, total = await harness.environment_service.list(workspace_id=ws_a.id)

    assert total == 1
    assert results[0].id == env_a.id


async def test_region_is_stored(harness):
    ws = await _make_workspace(harness)

    env = await harness.environment_service.register(workspace_id=ws.id, name="eu-prod", region="eu-west-1")

    assert env.region == "eu-west-1"
