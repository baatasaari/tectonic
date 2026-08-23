from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request

from tool_orchestration.app_context import AppContext
from tool_orchestration.clients.redis_circuit_breaker_store import RedisCircuitBreakerStore
from tool_orchestration.core.circuit_breaker import CircuitBreaker
from tool_orchestration.core.orchestration_service import ToolOrchestrationService
from tool_orchestration.core.ports import ToolRepository
from tool_orchestration.core.reliability_scorer import ReliabilityScorer
from tool_orchestration.core.retry_manager import RetryManager
from tool_orchestration.core.tool_synthesis import ToolSynthesisEngine
from tool_orchestration.db.repository import SQLAlchemyToolRepository


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


async def get_repository(request: Request) -> AsyncIterator[ToolRepository]:
    ctx: AppContext = request.app.state.ctx
    async with ctx.session_factory() as session:
        yield SQLAlchemyToolRepository(session)


async def build_orchestration_service(ctx: AppContext, repository: ToolRepository, tenant_id: str) -> ToolOrchestrationService:
    circuit_breaker = CircuitBreaker(ctx.settings.circuit_breaker)
    retry_manager = RetryManager(ctx.mcp_client, ctx.settings.retry)
    reliability_scorer = ReliabilityScorer()
    circuit_breaker_store = RedisCircuitBreakerStore(ctx.redis)
    return ToolOrchestrationService(repository, circuit_breaker_store, circuit_breaker, retry_manager, reliability_scorer)


def build_synthesis_engine(ctx: AppContext, repository: ToolRepository) -> ToolSynthesisEngine:
    return ToolSynthesisEngine(repository, ctx.llm_gateway, ctx.guardrails, ctx.sentinel, ctx.settings.synthesis)
