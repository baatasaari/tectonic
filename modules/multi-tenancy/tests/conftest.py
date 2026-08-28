from __future__ import annotations

import pytest

from multi_tenancy.core.environment_service import EnvironmentService
from multi_tenancy.core.fakes import (
    InMemoryMultiTenancyRepository,
    StubAuditabilityClient,
    StubTenantScopedListClient,
)
from multi_tenancy.core.isolation_probe_service import IsolationProbeService
from multi_tenancy.core.organisation_service import OrganisationService
from multi_tenancy.core.tenant_registry_service import TenantRegistryService
from multi_tenancy.core.workspace_service import WorkspaceService


class Harness:
    def __init__(self, **kwargs):
        self.repository = InMemoryMultiTenancyRepository()
        self.probe_clients = kwargs.get("probe_clients") or {"agent-cards": StubTenantScopedListClient()}
        self.auditability = kwargs.get("auditability") or StubAuditabilityClient()

        self.tenant_registry_service = TenantRegistryService(self.repository, self.auditability)
        self.isolation_probe_service = IsolationProbeService(self.repository, self.probe_clients)
        self.organisation_service = OrganisationService(self.repository, self.auditability)
        self.workspace_service = WorkspaceService(self.repository, self.auditability)
        self.environment_service = EnvironmentService(self.repository, self.auditability)


@pytest.fixture
def harness_factory():
    return Harness


@pytest.fixture
def harness():
    return Harness()
