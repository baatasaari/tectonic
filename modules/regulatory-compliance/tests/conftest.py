from __future__ import annotations

import pytest

from regulatory_compliance.core.crosswalk_engine import CoverageCalculator, CrosswalkEngine
from regulatory_compliance.core.domain import FrameworkProfileRecord, new_id
from regulatory_compliance.core.evidence_generator import EvidencePackGenerator
from regulatory_compliance.core.fakes import (
    InMemoryRegulatoryComplianceRepository,
    StubAuditabilityClient,
)
from regulatory_compliance.core.regulatory_feed import RegulatoryFeedManager


class Harness:
    def __init__(self, **kwargs):
        self.repository = InMemoryRegulatoryComplianceRepository()
        self.auditability = kwargs.get("auditability") or StubAuditabilityClient()

        self.crosswalk_engine = CrosswalkEngine(self.repository)
        self.coverage_calculator = CoverageCalculator(self.repository)
        self.feed_manager = RegulatoryFeedManager(self.repository)
        self.evidence_generator = EvidencePackGenerator(self.repository, self.auditability, kwargs.get("output_format", "json"))

    async def enable_framework(self, tenant_id: str, framework_name: str, version: str) -> FrameworkProfileRecord:
        record = FrameworkProfileRecord(id=new_id(), tenant_id=tenant_id, framework_name=framework_name, version=version)
        return await self.repository.create_framework_profile(record)


@pytest.fixture
def harness_factory():
    return Harness


@pytest.fixture
def harness():
    return Harness()
