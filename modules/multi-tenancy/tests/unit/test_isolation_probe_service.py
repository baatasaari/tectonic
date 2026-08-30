"""Tests for core/isolation_probe_service.py -- the real, executable
isolation check reused generically against any registered platform
module following the shared tenant-scoped list contract."""
from __future__ import annotations

import pytest

from multi_tenancy.core.domain import ProbeTargetNotFoundError
from multi_tenancy.core.fakes import StubTenantScopedListClient


async def test_run_probe_raises_for_an_unregistered_target(harness):
    with pytest.raises(ProbeTargetNotFoundError):
        await harness.isolation_probe_service.run_probe(tenant_id="acme", target_name="does-not-exist")


async def test_run_probe_passes_when_every_item_belongs_to_the_tenant(harness_factory):
    client = StubTenantScopedListClient(items=[{"id": "c1", "tenant_id": "acme"}, {"id": "c2", "tenant_id": "acme"}])
    h = harness_factory(probe_clients={"agent-cards": client})

    result = await h.isolation_probe_service.run_probe(tenant_id="acme", target_name="agent-cards")

    assert result.passed is True
    assert result.breach_count == 0
    assert result.sample_size == 2


async def test_run_probe_detects_a_breach(harness_factory):
    client = StubTenantScopedListClient(items=[
        {"id": "c1", "tenant_id": "acme"}, {"id": "c2", "tenant_id": "someone-else"},
    ])
    h = harness_factory(probe_clients={"agent-cards": client})

    result = await h.isolation_probe_service.run_probe(tenant_id="acme", target_name="agent-cards")

    assert result.passed is False
    assert result.breach_count == 1
    assert result.sample_size == 2
    assert "foreign record" in result.details


async def test_run_probe_fails_closed_when_the_target_is_unreachable(harness_factory):
    client = StubTenantScopedListClient(raise_error=True)
    h = harness_factory(probe_clients={"agent-cards": client})

    result = await h.isolation_probe_service.run_probe(tenant_id="acme", target_name="agent-cards")

    assert result.passed is False
    assert "probe_unavailable" in result.details


async def test_run_probe_passes_with_zero_items(harness_factory):
    client = StubTenantScopedListClient(items=[])
    h = harness_factory(probe_clients={"agent-cards": client})

    result = await h.isolation_probe_service.run_probe(tenant_id="acme", target_name="agent-cards")

    assert result.passed is True
    assert result.sample_size == 0


async def test_run_probe_persists_the_result(harness_factory):
    client = StubTenantScopedListClient(items=[{"id": "c1", "tenant_id": "acme"}])
    h = harness_factory(probe_clients={"agent-cards": client})

    result = await h.isolation_probe_service.run_probe(tenant_id="acme", target_name="agent-cards")

    results, total = await h.repository.list_probe_results(tenant_id="acme")
    assert total == 1
    assert results[0].id == result.id


async def test_run_probe_scopes_the_call_with_the_requested_tenant_id(harness_factory):
    client = StubTenantScopedListClient(items=[])
    h = harness_factory(probe_clients={"agent-cards": client})

    await h.isolation_probe_service.run_probe(tenant_id="acme", target_name="agent-cards")

    assert client.calls == [{"tenant_id": "acme"}]
