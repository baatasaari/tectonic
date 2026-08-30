"""Tests for core/resource_allocation_service.py -- the environment-scoped
canonical allocation object and its real request -> automated-or-manual-
approval -> active lifecycle.
"""
from __future__ import annotations

import pytest

from multi_tenancy.core.domain import (
    EnvironmentNotFoundError,
    InvalidTransitionError,
    ResourceAllocationNotFoundError,
    ResourceAllocationStatus,
)


async def _make_environment(harness):
    tenant = await harness.tenant_registry_service.register(name="Acme Corp")
    ws = await harness.workspace_service.register(tenant_id=tenant.id, name="Production workflows")
    return await harness.environment_service.register(workspace_id=ws.id, name="production", kind="production")


async def test_request_change_raises_for_an_unknown_environment(harness):
    with pytest.raises(EnvironmentNotFoundError):
        await harness.resource_allocation_service.request_change(
            environment_id="does-not-exist", resources={"cpu_cores": 4},
        )


async def test_first_ever_request_always_needs_approval(harness):
    """No baseline to compare an increase against -- even a small first
    request can't be treated as "a small change", so it always lands
    REQUESTED, never auto-approved."""
    env = await _make_environment(harness)

    allocation = await harness.resource_allocation_service.request_change(
        environment_id=env.id, resources={"cpu_cores": 1, "replicas": 1}, requested_by="alice",
    )

    assert allocation.status == ResourceAllocationStatus.REQUESTED
    assert allocation.approved_by is None
    assert allocation.requested_by == "alice"


async def test_request_change_emits_an_audit_event(harness):
    env = await _make_environment(harness)

    allocation = await harness.resource_allocation_service.request_change(
        environment_id=env.id, resources={"cpu_cores": 1},
    )

    events = [e for e in harness.auditability.events if e["event"] == "resource_allocation_requested"]
    assert len(events) == 1
    assert events[0]["allocation_id"] == allocation.id
    assert events[0]["status"] == "requested"


async def test_a_small_increase_over_an_active_baseline_is_auto_approved(harness):
    env = await _make_environment(harness)
    first = await harness.resource_allocation_service.request_change(
        environment_id=env.id, resources={"cpu_cores": 10},
    )
    await harness.resource_allocation_service.approve(first.id, approved_by="platform-admin", expected_version=1)

    second = await harness.resource_allocation_service.request_change(
        environment_id=env.id, resources={"cpu_cores": 11},  # a 10% increase
    )

    assert second.status == ResourceAllocationStatus.ACTIVE
    assert second.approved_by == "auto-policy"

    events = [e for e in harness.auditability.events if e["event"] == "resource_allocation_auto_approved"]
    assert len(events) == 1
    assert events[0]["allocation_id"] == second.id


async def test_a_large_increase_over_an_active_baseline_needs_approval(harness):
    env = await _make_environment(harness)
    first = await harness.resource_allocation_service.request_change(
        environment_id=env.id, resources={"cpu_cores": 10},
    )
    await harness.resource_allocation_service.approve(first.id, approved_by="platform-admin", expected_version=1)

    second = await harness.resource_allocation_service.request_change(
        environment_id=env.id, resources={"cpu_cores": 20},  # a 100% increase
    )

    assert second.status == ResourceAllocationStatus.REQUESTED


async def test_a_new_resource_class_never_seen_before_needs_approval(harness):
    env = await _make_environment(harness)
    first = await harness.resource_allocation_service.request_change(
        environment_id=env.id, resources={"cpu_cores": 10},
    )
    await harness.resource_allocation_service.approve(first.id, approved_by="platform-admin", expected_version=1)

    second = await harness.resource_allocation_service.request_change(
        environment_id=env.id, resources={"cpu_cores": 10, "gpu_count": 1},
    )

    assert second.status == ResourceAllocationStatus.REQUESTED


async def test_a_decrease_is_always_auto_approved(harness):
    env = await _make_environment(harness)
    first = await harness.resource_allocation_service.request_change(
        environment_id=env.id, resources={"cpu_cores": 10},
    )
    await harness.resource_allocation_service.approve(first.id, approved_by="platform-admin", expected_version=1)

    second = await harness.resource_allocation_service.request_change(
        environment_id=env.id, resources={"cpu_cores": 2},
    )

    assert second.status == ResourceAllocationStatus.ACTIVE


async def test_approve_then_reactivates_the_environments_current_allocation(harness):
    env = await _make_environment(harness)
    requested = await harness.resource_allocation_service.request_change(
        environment_id=env.id, resources={"cpu_cores": 4},
    )

    approved = await harness.resource_allocation_service.approve(requested.id, approved_by="platform-admin", expected_version=1)

    assert approved.status == ResourceAllocationStatus.ACTIVE
    assert approved.approved_by == "platform-admin"
    assert approved.version == 2

    events = [e for e in harness.auditability.events if e["event"] == "resource_allocation_approved"]
    assert len(events) == 1


async def test_approve_raises_for_an_unknown_allocation(harness):
    with pytest.raises(ResourceAllocationNotFoundError):
        await harness.resource_allocation_service.approve("does-not-exist", approved_by="platform-admin", expected_version=1)


async def test_approve_is_not_legal_on_an_already_active_allocation(harness):
    env = await _make_environment(harness)
    requested = await harness.resource_allocation_service.request_change(
        environment_id=env.id, resources={"cpu_cores": 4},
    )
    await harness.resource_allocation_service.approve(requested.id, approved_by="platform-admin", expected_version=1)

    with pytest.raises(InvalidTransitionError):
        await harness.resource_allocation_service.approve(requested.id, approved_by="platform-admin", expected_version=2)


async def test_reject_stores_the_reason(harness):
    env = await _make_environment(harness)
    requested = await harness.resource_allocation_service.request_change(
        environment_id=env.id, resources={"cpu_cores": 4},
    )

    rejected = await harness.resource_allocation_service.reject(requested.id, reason="over regional capacity", expected_version=1)

    assert rejected.status == ResourceAllocationStatus.REJECTED
    assert rejected.rejection_reason == "over regional capacity"

    events = [e for e in harness.auditability.events if e["event"] == "resource_allocation_rejected"]
    assert events[0]["reason"] == "over regional capacity"


async def test_reject_is_not_legal_on_an_already_rejected_allocation(harness):
    env = await _make_environment(harness)
    requested = await harness.resource_allocation_service.request_change(
        environment_id=env.id, resources={"cpu_cores": 4},
    )
    await harness.resource_allocation_service.reject(requested.id, reason="no", expected_version=1)

    with pytest.raises(InvalidTransitionError):
        await harness.resource_allocation_service.reject(requested.id, reason="still no", expected_version=2)


async def test_get_raises_for_an_unknown_allocation(harness):
    with pytest.raises(ResourceAllocationNotFoundError):
        await harness.resource_allocation_service.get("does-not-exist")


async def test_list_filters_by_environment_and_status(harness):
    env_a = await _make_environment(harness)
    env_b = await _make_environment(harness)
    allocation_a = await harness.resource_allocation_service.request_change(
        environment_id=env_a.id, resources={"cpu_cores": 4},
    )
    await harness.resource_allocation_service.request_change(environment_id=env_b.id, resources={"cpu_cores": 4})

    results, total = await harness.resource_allocation_service.list(environment_id=env_a.id)

    assert total == 1
    assert results[0].id == allocation_a.id


async def test_a_stale_expected_version_is_rejected_at_the_repository_layer(harness):
    """Real race this ticket's optimistic-concurrency enforcement exists
    to catch: two reviewers both looking at the same REQUESTED
    allocation (both read version=1), one approving and one rejecting
    nearly simultaneously -- whichever commits first wins for real, the
    second's decision must be rejected rather than silently overwriting
    the first. Exercised directly against the repository, bypassing
    `ResourceAllocationService`'s own `status != REQUESTED` guard --
    in this single-threaded test harness, two sequential *service*-level
    calls always serialize (the second call's own fresh `get()` sees
    the first call's already-committed status, so the legality guard
    catches it before ever reaching the compare-and-swap). The real
    *concurrent*-caller proof runs against real Postgres in the
    integration tier."""
    from multi_tenancy.core.domain import OptimisticConcurrencyError

    env = await _make_environment(harness)
    requested = await harness.resource_allocation_service.request_change(
        environment_id=env.id, resources={"cpu_cores": 4},
    )
    approved = await harness.resource_allocation_service.approve(
        requested.id, approved_by="reviewer-a", expected_version=1,
    )
    assert approved.status == ResourceAllocationStatus.ACTIVE

    stale = await harness.repository.get_resource_allocation(requested.id)
    stale.status = ResourceAllocationStatus.REJECTED
    stale.rejection_reason = "reviewer-b's stale decision"
    with pytest.raises(OptimisticConcurrencyError):
        await harness.repository.update_resource_allocation(stale, expected_version=1)  # real version is now 2

    final = await harness.resource_allocation_service.get(requested.id)
    assert final.status == ResourceAllocationStatus.ACTIVE
    assert final.approved_by == "reviewer-a"
