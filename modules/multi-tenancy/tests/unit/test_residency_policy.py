"""Tests for real data-residency enforcement (independent architecture
assessment §3.4 point 5): ResidencyPolicyService's own CRUD, and the
real enforcement point -- EnvironmentService.register.
"""
from __future__ import annotations

import pytest

from multi_tenancy.core.domain import ResidencyPolicyViolationError, WorkspaceNotFoundError


async def _make_workspace(harness, **tenant_overrides):
    tenant = await harness.tenant_registry_service.register(name="Acme Corp", **tenant_overrides)
    return await harness.workspace_service.register(tenant_id=tenant.id, name="Production workflows")


async def test_get_returns_none_for_an_unconfigured_tenant(harness):
    tenant = await harness.tenant_registry_service.register(name="Acme Corp")

    policy = await harness.residency_policy_service.get(tenant.id)

    assert policy is None


async def test_set_allowed_regions_creates_and_stamps_configured_at(harness):
    tenant = await harness.tenant_registry_service.register(name="Acme Corp")

    policy = await harness.residency_policy_service.set_allowed_regions(
        tenant.id, allowed_regions=["eu-west-1", "eu-central-1"],
    )

    assert policy.allowed_regions == ["eu-west-1", "eu-central-1"]
    assert policy.configured_at is not None
    assert policy.version == 1


async def test_set_allowed_regions_replaces_wholesale(harness):
    tenant = await harness.tenant_registry_service.register(name="Acme Corp")
    await harness.residency_policy_service.set_allowed_regions(tenant.id, allowed_regions=["eu-west-1", "us-east-1"])

    replaced = await harness.residency_policy_service.set_allowed_regions(tenant.id, allowed_regions=["eu-west-1"])

    assert replaced.allowed_regions == ["eu-west-1"]  # us-east-1 gone, not merged
    assert replaced.version == 2


async def test_environment_registration_is_unrestricted_for_an_unconfigured_tenant(harness):
    """Rollout-safety default: a tenant that never configured a
    residency policy is unrestricted, not silently locked to zero
    regions."""
    ws = await _make_workspace(harness)

    env = await harness.environment_service.register(workspace_id=ws.id, name="prod", region="ap-southeast-1")

    assert env.region == "ap-southeast-1"


async def test_environment_registration_rejects_a_disallowed_region(harness):
    tenant = await harness.tenant_registry_service.register(name="Acme Corp")
    ws = await harness.workspace_service.register(tenant_id=tenant.id, name="Production")
    await harness.residency_policy_service.set_allowed_regions(tenant.id, allowed_regions=["eu-west-1"])

    with pytest.raises(ResidencyPolicyViolationError):
        await harness.environment_service.register(workspace_id=ws.id, name="prod-us", region="us-east-1")


async def test_environment_registration_accepts_an_allowed_region(harness):
    tenant = await harness.tenant_registry_service.register(name="Acme Corp")
    ws = await harness.workspace_service.register(tenant_id=tenant.id, name="Production")
    await harness.residency_policy_service.set_allowed_regions(tenant.id, allowed_regions=["eu-west-1"])

    env = await harness.environment_service.register(workspace_id=ws.id, name="prod-eu", region="eu-west-1")

    assert env.region == "eu-west-1"


async def test_environment_registration_with_no_region_bypasses_the_check(harness):
    """No region claim is being made at all -- nothing to validate
    against, even for a tenant with a configured, restrictive policy."""
    tenant = await harness.tenant_registry_service.register(name="Acme Corp")
    ws = await harness.workspace_service.register(tenant_id=tenant.id, name="Production")
    await harness.residency_policy_service.set_allowed_regions(tenant.id, allowed_regions=["eu-west-1"])

    env = await harness.environment_service.register(workspace_id=ws.id, name="prod")

    assert env.region is None


async def test_an_explicit_empty_allowed_regions_denies_every_region(harness):
    """The same real-vs-unconfigured distinction QuotaSet/entitlements
    already establish: an explicit empty list is a real, meaningful
    'no region permitted' policy, not the same as never having
    configured one."""
    tenant = await harness.tenant_registry_service.register(name="Acme Corp")
    ws = await harness.workspace_service.register(tenant_id=tenant.id, name="Production")
    await harness.residency_policy_service.set_allowed_regions(tenant.id, allowed_regions=[])

    with pytest.raises(ResidencyPolicyViolationError):
        await harness.environment_service.register(workspace_id=ws.id, name="prod-eu", region="eu-west-1")


async def test_register_still_raises_workspace_not_found_before_checking_residency(harness):
    with pytest.raises(WorkspaceNotFoundError):
        await harness.environment_service.register(workspace_id="does-not-exist", name="prod", region="eu-west-1")
