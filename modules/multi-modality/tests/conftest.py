from __future__ import annotations

import pytest

from multi_modality.core.extraction_service import ExtractionService
from multi_modality.core.extractors import default_extractors
from multi_modality.core.fakes import InMemoryMultiModalityRepository, StubGuardrailsClient


class Harness:
    def __init__(self, **kwargs):
        self.repository = InMemoryMultiModalityRepository()
        self.guardrails = kwargs.get("guardrails") or StubGuardrailsClient()
        self.extraction_service = ExtractionService(self.repository, self.guardrails, default_extractors())


@pytest.fixture
def harness_factory():
    return Harness


@pytest.fixture
def harness():
    return Harness()
