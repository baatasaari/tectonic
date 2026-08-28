"""Tests for core/tenant_registry_service.py -- register/suspend/
reactivate/delete and the tenant lifecycle state machine, plus the
`gate` check other modules should call before serving a request."""
from __future__ import annotations

import pytest

from multi_tenancy.core.domain import InvalidTransitionError, TenantNotFoundError, TenantStatus


async def test_register_starts_active(harness):
    tenant = await harness.tenant_registry_service.register(name="Acme Corp", tier="enterprise")

    assert tenant.status == TenantStatus.ACTIVE
    assert tenant.tier == "enterprise"
    assert tenant.organisation_id is None

    fetched = await harness.tenant_registry_service.get(tenant.id)
    assert fetched.id == tenant.id


async def test_register_stores_an_organisation_id_when_given(harness):
    org = await harness.organisation_service.register(name="Acme Holdings")

    tenant = await harness.tenant_registry_service.register(name="Acme Corp", organisation_id=org.id)

    assert tenant.organisation_id == org.id


async def test_register_emits_an_audit_event(harness):
    tenant = await harness.tenant_registry_service.register(name="Acme Corp")

    events = [e for e in harness.auditability.events if e["event"] == "tenant_created"]
    assert len(events) == 1
    assert events[0]["tenant_id"] == tenant.id


async def test_status_transitions_emit_audit_events(harness):
    tenant = await harness.tenant_registry_service.register(name="Acme Corp")
    await harness.tenant_registry_service.suspend(tenant.id, reason="non-payment")

    events = [e for e in harness.auditability.events if e["event"] == "tenant_status_changed"]
    assert len(events) == 1
    assert events[0] == {
        "event": "tenant_status_changed", "tenant_id": tenant.id, "from_status": "active", "to_status": "suspended",
    }


async def test_get_raises_when_missing(harness):
    with pytest.raises(TenantNotFoundError):
        await harness.tenant_registry_service.get("does-not-exist")


async def test_suspend_then_reactivate(harness):
    tenant = await harness.tenant_registry_service.register(name="Acme Corp")

    suspended = await harness.tenant_registry_service.suspend(tenant.id, reason="non-payment")
    assert suspended.status == TenantStatus.SUSPENDED

    reactivated = await harness.tenant_registry_service.reactivate(tenant.id)
    assert reactivated.status == TenantStatus.ACTIVE


async def test_delete_is_terminal(harness):
    tenant = await harness.tenant_registry_service.register(name="Acme Corp")
    await harness.tenant_registry_service.delete(tenant.id)

    with pytest.raises(InvalidTransitionError):
        await harness.tenant_registry_service.reactivate(tenant.id)

    with pytest.raises(InvalidTransitionError):
        await harness.tenant_registry_service.suspend(tenant.id, reason="anything")


async def test_reactivate_on_an_active_tenant_is_illegal(harness):
    tenant = await harness.tenant_registry_service.register(name="Acme Corp")

    with pytest.raises(InvalidTransitionError):
        await harness.tenant_registry_service.reactivate(tenant.id)


async def test_list_filters_by_status(harness):
    a = await harness.tenant_registry_service.register(name="Active Co")
    b = await harness.tenant_registry_service.register(name="Suspended Co")
    await harness.tenant_registry_service.suspend(b.id, reason="fraud review")

    active_only, total = await harness.tenant_registry_service.list(status=TenantStatus.ACTIVE)

    assert total == 1
    assert active_only[0].id == a.id


async def test_gate_allows_an_active_tenant(harness):
    tenant = await harness.tenant_registry_service.register(name="Acme Corp")

    result = await harness.tenant_registry_service.gate(tenant.id)

    assert result.allowed is True


async def test_gate_denies_a_suspended_tenant(harness):
    tenant = await harness.tenant_registry_service.register(name="Acme Corp")
    await harness.tenant_registry_service.suspend(tenant.id, reason="non-payment")

    result = await harness.tenant_registry_service.gate(tenant.id)

    assert result.allowed is False
    assert "suspended" in result.reason


async def test_gate_denies_an_unknown_tenant(harness):
    result = await harness.tenant_registry_service.gate("does-not-exist")

    assert result.allowed is False
    assert "unknown" in result.reason


async def test_gate_denies_a_deleted_tenant(harness):
    tenant = await harness.tenant_registry_service.register(name="Acme Corp")
    await harness.tenant_registry_service.delete(tenant.id)

    result = await harness.tenant_registry_service.gate(tenant.id)

    assert result.allowed is False
    assert "deleted" in result.reason


async def test_gate_with_module_allows_an_unconfigured_tenant(harness):
    """A tenant that has never had entitlements set is ungated -- every
    module is allowed. This is the rollout-safety default: shipping the
    entitlement check must never silently start denying pre-existing
    tenants."""
    tenant = await harness.tenant_registry_service.register(name="Acme Corp")

    result = await harness.tenant_registry_service.gate(tenant.id, module="agent-cards")

    assert result.allowed is True


async def test_gate_with_module_allows_an_entitled_module(harness):
    tenant = await harness.tenant_registry_service.register(name="Acme Corp")
    await harness.tenant_registry_service.set_entitlements(tenant.id, module_names=["agent-cards", "guardrails"])

    result = await harness.tenant_registry_service.gate(tenant.id, module="agent-cards")

    assert result.allowed is True


async def test_gate_with_module_denies_a_module_not_in_the_plan(harness):
    tenant = await harness.tenant_registry_service.register(name="Acme Corp")
    await harness.tenant_registry_service.set_entitlements(tenant.id, module_names=["guardrails"])

    result = await harness.tenant_registry_service.gate(tenant.id, module="agent-cards")

    assert result.allowed is False
    assert "agent-cards" in result.reason


async def test_gate_with_module_denies_every_module_for_an_explicit_empty_plan(harness):
    """A tenant explicitly configured with zero modules is not the same
    as an unconfigured tenant -- it denies everything, per the docstring
    on TenantRecord.entitlements_configured_at."""
    tenant = await harness.tenant_registry_service.register(name="Acme Corp")
    await harness.tenant_registry_service.set_entitlements(tenant.id, module_names=[])

    result = await harness.tenant_registry_service.gate(tenant.id, module="agent-cards")

    assert result.allowed is False


async def test_gate_without_a_module_ignores_entitlements(harness):
    """Callers that only care about tenant status (not a specific
    module) keep working unchanged, even for a tenant with a
    restrictive entitlement set."""
    tenant = await harness.tenant_registry_service.register(name="Acme Corp")
    await harness.tenant_registry_service.set_entitlements(tenant.id, module_names=[])

    result = await harness.tenant_registry_service.gate(tenant.id)

    assert result.allowed is True


async def test_set_entitlements_replaces_wholesale(harness):
    tenant = await harness.tenant_registry_service.register(name="Acme Corp")
    await harness.tenant_registry_service.set_entitlements(tenant.id, module_names=["agent-cards", "guardrails"])

    replaced = await harness.tenant_registry_service.set_entitlements(tenant.id, module_names=["guardrails"])

    assert {e.module_name for e in replaced} == {"guardrails"}
    listed = await harness.tenant_registry_service.list_entitlements(tenant.id)
    assert {e.module_name for e in listed} == {"guardrails"}


async def test_set_entitlements_raises_for_an_unknown_tenant(harness):
    with pytest.raises(TenantNotFoundError):
        await harness.tenant_registry_service.set_entitlements("does-not-exist", module_names=["agent-cards"])


async def test_list_entitlements_raises_for_an_unknown_tenant(harness):
    with pytest.raises(TenantNotFoundError):
        await harness.tenant_registry_service.list_entitlements("does-not-exist")
