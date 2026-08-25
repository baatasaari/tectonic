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

    fetched = await harness.tenant_registry_service.get(tenant.id)
    assert fetched.id == tenant.id


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
