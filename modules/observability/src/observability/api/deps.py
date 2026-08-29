from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request

from observability.app_context import AppContext
from observability.core.alerting_service import AlertingService
from observability.core.completeness import TraceCompletenessCalculator
from observability.core.cost_attribution import CostAttributionJoiner
from observability.core.ingestion import IngestionService
from observability.core.ports import ObservabilityRepository
from observability.core.reasoning_reconstructor import ReasoningTraceReconstructor
from observability.core.slo_service import SLOService
from observability.db.repository import SQLAlchemyObservabilityRepository


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


async def get_repository(request: Request) -> AsyncIterator[ObservabilityRepository]:
    ctx: AppContext = request.app.state.ctx
    async with ctx.session_factory() as session:
        yield SQLAlchemyObservabilityRepository(session)


def build_ingestion_service(repository: ObservabilityRepository) -> IngestionService:
    return IngestionService(repository)


def build_reasoning_reconstructor(ctx: AppContext) -> ReasoningTraceReconstructor:
    return ReasoningTraceReconstructor(ctx.llm_gateway, enabled=ctx.settings.reasoning_narrative.enabled)


def build_cost_attribution_joiner() -> CostAttributionJoiner:
    return CostAttributionJoiner()


def build_completeness_calculator(ctx: AppContext, repository: ObservabilityRepository) -> TraceCompletenessCalculator:
    return TraceCompletenessCalculator(repository, ctx.settings.workflow_shapes.expected_spans)


def build_slo_service(repository: ObservabilityRepository) -> SLOService:
    return SLOService(repository)


def build_alerting_service(repository: ObservabilityRepository) -> AlertingService:
    return AlertingService(repository)
