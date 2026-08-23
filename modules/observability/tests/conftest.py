from __future__ import annotations

import pytest

from observability.core.completeness import TraceCompletenessCalculator
from observability.core.cost_attribution import CostAttributionJoiner
from observability.core.domain import SpanRecord, now
from observability.core.fakes import InMemoryObservabilityRepository, StubLLMGatewayClient
from observability.core.ingestion import IngestionService
from observability.core.reasoning_reconstructor import ReasoningTraceReconstructor


class Harness:
    def __init__(self, **kwargs):
        self.repository = InMemoryObservabilityRepository()
        self.llm_gateway = kwargs.get("llm_gateway") or StubLLMGatewayClient()
        self.expected_spans = kwargs.get("expected_spans") or {}

        self.ingestion_service = IngestionService(self.repository)
        self.reconstructor = ReasoningTraceReconstructor(self.llm_gateway, enabled=kwargs.get("narrative_enabled", True))
        self.cost_joiner = CostAttributionJoiner()
        self.completeness_calculator = TraceCompletenessCalculator(self.repository, self.expected_spans)

    async def add_span(self, tenant_id: str, trace_id: str, span_id: str, name: str, **overrides) -> SpanRecord:
        base = now()
        record = SpanRecord(
            id=f"{trace_id}:{span_id}", tenant_id=tenant_id, trace_id=trace_id, span_id=span_id,
            parent_span_id=overrides.pop("parent_span_id", None), name=name,
            service_name=overrides.pop("service_name", "workflow-engine"), start_time=base,
            end_time=overrides.pop("end_time", base), attributes=overrides.pop("attributes", {}),
            status=overrides.pop("status", "ok"), workflow_type=overrides.pop("workflow_type", None),
        )
        return await self.repository.create_span(record)


@pytest.fixture
def harness_factory():
    return Harness


@pytest.fixture
def harness():
    return Harness()
