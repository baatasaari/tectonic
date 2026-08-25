from __future__ import annotations

import pytest

from multi_tenancy.core.fakes import InMemoryMultiTenancyRepository, StubTenantScopedListClient
from multi_tenancy.core.isolation_probe_service import IsolationProbeService
from multi_tenancy.core.tenant_registry_service import TenantRegistryService


class Harness:
    def __init__(self, **kwargs):
        self.repository = InMemoryMultiTenancyRepository()
        self.probe_clients = kwargs.get("probe_clients") or {"agent-cards": StubTenantScopedListClient()}

        self.tenant_registry_service = TenantRegistryService(self.repository)
        self.isolation_probe_service = IsolationProbeService(self.repository, self.probe_clients)


@pytest.fixture
def harness_factory():
    return Harness


@pytest.fixture
def harness():
    return Harness()
