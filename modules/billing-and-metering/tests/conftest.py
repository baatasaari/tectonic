from __future__ import annotations

import pytest

from billing_and_metering.core.fakes import (
    InMemoryBillingRepository,
    StubAuditabilityClient,
    StubFinOpsClient,
    StubMultiTenancyClient,
)
from billing_and_metering.core.invoice_service import InvoiceService
from billing_and_metering.core.metering_service import MeteringService
from billing_and_metering.core.pricing_plan_service import PricingPlanService


class Harness:
    def __init__(self, **kwargs):
        self.repository = InMemoryBillingRepository()
        self.finops = kwargs.get("finops") or StubFinOpsClient()
        self.auditability = kwargs.get("auditability") or StubAuditabilityClient()
        self.multi_tenancy = kwargs.get("multi_tenancy") or StubMultiTenancyClient()

        self.pricing_plan_service = PricingPlanService(self.repository, self.multi_tenancy)
        self.metering_service = MeteringService(self.repository, self.finops, self.auditability, self.multi_tenancy)
        self.invoice_service = InvoiceService(self.repository, self.pricing_plan_service, self.metering_service)


@pytest.fixture
def harness_factory():
    return Harness


@pytest.fixture
def harness():
    return Harness()
