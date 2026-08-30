from __future__ import annotations

import pytest

from auditability.core.audit_pack_generator import AuditPackGenerator
from auditability.core.fakes import InMemoryAuditabilityRepository, StubLLMGatewayClient
from auditability.core.ingestion_service import IngestionService
from auditability.core.nl_query_translator import NLQueryTranslator


class Harness:
    def __init__(self, **kwargs):
        self.repository = InMemoryAuditabilityRepository()
        self.llm_gateway = kwargs.get("llm_gateway") or StubLLMGatewayClient()

        self.ingestion_service = IngestionService(self.repository)
        self.nl_query_translator = NLQueryTranslator(self.llm_gateway)
        self.audit_pack_generator = AuditPackGenerator(self.repository, kwargs.get("output_format", "json"))


@pytest.fixture
def harness_factory():
    return Harness


@pytest.fixture
def harness():
    return Harness()
