"""Tests for core/organisation_service.py -- register/suspend/reactivate/
delete for the top level of the platform hierarchy (Organisation ->
Tenant -> Workspace -> Environment), and that every lifecycle event
emits a real Auditability event.
"""
from __future__ import annotations

import pytest

from multi_tenancy.core.domain import (
    HierarchyStatus,
    InvalidTransitionError,
    OrganisationNotFoundError,
)


async def test_register_starts_active(harness):
    org = await harness.organisation_service.register(name="Acme Holdings")

    assert org.status == HierarchyStatus.ACTIVE
    assert org.version == 1

    fetched = await harness.organisation_service.get(org.id)
    assert fetched.id == org.id


async def test_register_emits_an_audit_event(harness):
    org = await harness.organisation_service.register(name="Acme Holdings")

    events = [e for e in harness.auditability.events if e["event"] == "organisation_created"]
    assert len(events) == 1
    assert events[0]["organisation_id"] == org.id


async def test_get_raises_when_missing(harness):
    with pytest.raises(OrganisationNotFoundError):
        await harness.organisation_service.get("does-not-exist")


async def test_suspend_then_reactivate(harness):
    org = await harness.organisation_service.register(name="Acme Holdings")

    suspended = await harness.organisation_service.suspend(org.id, reason="fraud review")
    assert suspended.status == HierarchyStatus.SUSPENDED
    assert suspended.version == 2

    reactivated = await harness.organisation_service.reactivate(org.id)
    assert reactivated.status == HierarchyStatus.ACTIVE
    assert reactivated.version == 3


async def test_transitions_emit_audit_events(harness):
    org = await harness.organisation_service.register(name="Acme Holdings")
    await harness.organisation_service.suspend(org.id, reason="fraud review")

    events = [e for e in harness.auditability.events if e["event"] == "organisation_status_changed"]
    assert len(events) == 1
    assert events[0] == {
        "event": "organisation_status_changed", "organisation_id": org.id,
        "from_status": "active", "to_status": "suspended",
    }


async def test_delete_is_terminal(harness):
    org = await harness.organisation_service.register(name="Acme Holdings")
    await harness.organisation_service.delete(org.id)

    with pytest.raises(InvalidTransitionError):
        await harness.organisation_service.reactivate(org.id)


async def test_list_filters_by_status(harness):
    a = await harness.organisation_service.register(name="Active Holdings")
    b = await harness.organisation_service.register(name="Suspended Holdings")
    await harness.organisation_service.suspend(b.id, reason="review")

    active_only, total = await harness.organisation_service.list(status=HierarchyStatus.ACTIVE)

    assert total == 1
    assert active_only[0].id == a.id


async def test_owner_identity_id_is_stored(harness):
    org = await harness.organisation_service.register(name="Acme Holdings", owner_identity_id="identity-1")

    assert org.owner_identity_id == "identity-1"
