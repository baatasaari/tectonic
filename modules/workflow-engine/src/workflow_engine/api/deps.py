from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from workflow_engine.app_context import AppContext
from workflow_engine.core.human import HumanApprovalHandler
from workflow_engine.core.neural import NeuralStepExecutor
from workflow_engine.core.ports import WorkflowRepository
from workflow_engine.core.replanner import Replanner
from workflow_engine.core.scheduler import ExecutionScheduler
from workflow_engine.db.repository import SQLAlchemyWorkflowRepository


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    ctx: AppContext = request.app.state.ctx
    async with ctx.session_factory() as session:
        yield session


async def get_repository(request: Request) -> AsyncIterator[WorkflowRepository]:
    ctx: AppContext = request.app.state.ctx
    async with ctx.session_factory() as session:
        yield SQLAlchemyWorkflowRepository(session)


def build_scheduler(ctx: AppContext, repository: WorkflowRepository) -> ExecutionScheduler:
    neural_executor = NeuralStepExecutor(
        ctx.llm_gateway, ctx.tool_orchestration, ctx.guardrails,
        intent_detection=ctx.intent_detection, agentic_rag=ctx.agentic_rag,
    )
    human_handler = HumanApprovalHandler(repository, ctx.human_oversight)
    replanner = Replanner(repository, ctx.llm_gateway)
    return ExecutionScheduler(
        repository=repository,
        event_publisher=ctx.event_publisher,
        symbolic_executor=ctx.symbolic_executor,
        neural_executor=neural_executor,
        human_handler=human_handler,
        replanner=replanner,
        execution_config=ctx.settings.execution,
        replanning_config=ctx.settings.replanning,
    )
