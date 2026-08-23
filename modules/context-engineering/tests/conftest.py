from __future__ import annotations

import pytest

from context_engineering.config import BudgetConfig, PrioritisationConfig
from context_engineering.core.compression import CompressionService
from context_engineering.core.context_assembly_service import ContextAssemblyService
from context_engineering.core.fakes import InMemoryContextRepository, StubLLMGatewayClient
from context_engineering.core.ontology_filter import OntologyFilter
from context_engineering.core.prioritisation_engine import PrioritisationEngine
from context_engineering.core.token_budget_enforcer import TokenBudgetEnforcer
from context_engineering.core.tokenization import SimpleTokenCounter


class Harness:
    def __init__(self, **kwargs):
        self.repository = InMemoryContextRepository()
        self.llm_gateway = kwargs.get("llm_gateway") or StubLLMGatewayClient()
        self.token_counter = SimpleTokenCounter()
        self.ontology_filter = OntologyFilter()
        self.prioritisation_engine = PrioritisationEngine()
        self.budget_enforcer = TokenBudgetEnforcer(self.token_counter)
        self.compression_service = CompressionService(self.llm_gateway, self.token_counter)
        self.prioritisation_config = kwargs.get("prioritisation_config") or PrioritisationConfig()
        self.budget_config = kwargs.get("budget_config") or BudgetConfig()

        self.service = ContextAssemblyService(
            repository=self.repository,
            ontology_filter=self.ontology_filter,
            prioritisation_engine=self.prioritisation_engine,
            budget_enforcer=self.budget_enforcer,
            compression_service=self.compression_service,
            prioritisation_config=self.prioritisation_config,
            budget_config=self.budget_config,
        )


@pytest.fixture
def harness_factory():
    return Harness


@pytest.fixture
def harness():
    return Harness()
