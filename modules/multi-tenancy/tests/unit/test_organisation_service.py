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
    OptimisticConcurrencyError,
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

    suspended = await harness.organisation_service.suspend(org.id, reason="fraud review", expected_version=1)
    assert suspended.status == HierarchyStatus.SUSPENDED
    assert suspended.version == 2

    reactivated = await harness.organisation_service.reactivate(org.id, expected_version=2)
    assert reactivated.status == HierarchyStatus.ACTIVE
    assert reactivated.version == 3


async def test_transitions_emit_audit_events(harness):
    org = await harness.organisation_service.register(name="Acme Holdings")
    await harness.organisation_service.suspend(org.id, reason="fraud review", expected_version=1)

    events = [e for e in harness.auditability.events if e["event"] == "organisation_status_changed"]
    assert len(events) == 1
    assert events[0] == {
        "event": "organisation_status_changed", "organisation_id": org.id,
        "from_status": "active", "to_status": "suspended",
    }


async def test_delete_is_terminal(harness):
    org = await harness.organisation_service.register(name="Acme Holdings")
    await harness.organisation_service.delete(org.id, expected_version=1)

    with pytest.raises(InvalidTransitionError):
        await harness.organisation_service.reactivate(org.id, expected_version=2)


async def test_list_filters_by_status(harness):
    a = await harness.organisation_service.register(name="Active Holdings")
    b = await harness.organisation_service.register(name="Suspended Holdings")
    await harness.organisation_service.suspend(b.id, reason="review", expected_version=1)

    active_only, total = await harness.organisation_service.list(status=HierarchyStatus.ACTIVE)

    assert total == 1
    assert active_only[0].id == a.id


async def test_suspend_with_a_stale_expected_version_raises(harness):
    org = await harness.organisation_service.register(name="Acme Holdings")
    await harness.organisation_service.suspend(org.id, reason="first update", expected_version=1)

    with pytest.raises(OptimisticConcurrencyError):
        # A second caller who read version=1 before the first suspend landed --
        # exactly the race this exists to catch.
        await harness.organisation_service.reactivate(org.id, expected_version=1)


async def test_a_stale_expected_version_is_rejected_at_the_repository_layer(harness):
    """Exercises the real compare-and-swap directly against the
    repository, bypassing `OrganisationService`'s own
    `is_legal_hierarchy_transition` guard -- in this single-threaded
    test harness, two sequential *service*-level calls always serialize
    (the second call's own fresh `get()` sees the first call's already-
    committed status, so the legality guard catches it before ever
    reaching the compare-and-swap), so the repository is where a
    genuinely stale `expected_version` can actually be proven rejected
    at unit-test speed. The real *concurrent*-caller proof (two truly
    simultaneous writers, one winning) runs against real Postgres in
    the integration tier."""
    org = await harness.organisation_service.register(name="Acme Holdings")
    stored = await harness.repository.get_organisation(org.id)

    stored.status = HierarchyStatus.SUSPENDED
    updated = await harness.repository.update_organisation(stored, expected_version=1)
    assert updated.version == 2

    stored.status = HierarchyStatus.ACTIVE
    with pytest.raises(OptimisticConcurrencyError):
        await harness.repository.update_organisation(stored, expected_version=1)  # stale -- real version is now 2

    current = await harness.organisation_service.get(org.id)
    assert current.status == HierarchyStatus.SUSPENDED  # the stale write never landed
    assert current.version == 2


async def test_owner_identity_id_is_stored(harness):
    org = await harness.organisation_service.register(name="Acme Holdings", owner_identity_id="identity-1")

    assert org.owner_identity_id == "identity-1"
