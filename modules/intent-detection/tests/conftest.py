from __future__ import annotations

import pytest

from intent_detection.config import ClassificationConfig
from intent_detection.core.classification_service import ClassificationService
from intent_detection.core.compositional_decomposer import CompositionalDecomposer
from intent_detection.core.domain import (
    IntentDefinition,
    IntentTaxonomyRecord,
    TaxonomyStatus,
    new_id,
)
from intent_detection.core.fakes import InMemoryIntentRepository, StubLLMGatewayClient
from intent_detection.core.llm_fallback import LLMFallbackHandler
from intent_detection.core.primary_classifier import PrimaryClassifier


class Harness:
    def __init__(self, **kwargs):
        self.repository = InMemoryIntentRepository()
        self.llm_gateway = kwargs.get("llm_gateway") or StubLLMGatewayClient()
        self.primary_classifier = PrimaryClassifier()
        self.decomposer = CompositionalDecomposer()
        self.fallback_handler = LLMFallbackHandler(self.llm_gateway)
        self.config = kwargs.get("config") or ClassificationConfig()

        self.service = ClassificationService(
            self.repository, self.primary_classifier, self.decomposer, self.fallback_handler, self.config
        )

    async def seed_taxonomy(self, tenant_id: str = "tenant-a", version: int = 1, intents: list[IntentDefinition] | None = None) -> IntentTaxonomyRecord:
        record = IntentTaxonomyRecord(
            id=new_id(),
            tenant_id=tenant_id,
            version=version,
            intents=intents or [
                IntentDefinition(name="check_balance", examples=["what is my account balance", "check my balance"]),
                IntentDefinition(name="update_address", examples=["update my address", "change my mailing address"]),
                IntentDefinition(name="close_account", examples=["close my account", "cancel my account"]),
            ],
            status=TaxonomyStatus.ACTIVE,
        )
        return await self.repository.create_taxonomy(record)


@pytest.fixture
def harness_factory():
    return Harness


@pytest.fixture
def harness():
    return Harness()
