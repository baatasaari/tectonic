from __future__ import annotations

import pytest

from sdk_and_developer_portal.core.adoption_metrics_service import AdoptionMetricsService
from sdk_and_developer_portal.core.developer_account_service import DeveloperAccountService
from sdk_and_developer_portal.core.fakes import (
    InMemoryPortalRepository,
    StubAuditabilityClient,
    StubIdentityAccessClient,
    StubModuleSpecClient,
    StubMultiTenancyClient,
)
from sdk_and_developer_portal.core.module_catalog_service import ModuleCatalogService
from sdk_and_developer_portal.core.sdk_generator_service import SdkGeneratorService


class Harness:
    def __init__(self, **kwargs):
        self.repository = InMemoryPortalRepository()
        self.identity_access = kwargs.get("identity_access") or StubIdentityAccessClient()
        self.multi_tenancy = kwargs.get("multi_tenancy") or StubMultiTenancyClient()
        self.auditability = kwargs.get("auditability") or StubAuditabilityClient()
        self.module_spec = kwargs.get("module_spec") or StubModuleSpecClient()

        self.developer_service = DeveloperAccountService(self.repository, self.identity_access, self.multi_tenancy)
        self.catalog_service = ModuleCatalogService(self.repository, self.module_spec)
        self.sdk_service = SdkGeneratorService(self.repository, self.catalog_service)
        self.adoption_service = AdoptionMetricsService(self.repository, self.auditability)


@pytest.fixture
def harness_factory():
    return Harness


@pytest.fixture
def harness():
    return Harness()
