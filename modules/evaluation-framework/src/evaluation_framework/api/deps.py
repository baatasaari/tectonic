from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request

from evaluation_framework.app_context import AppContext
from evaluation_framework.core.evaluator import Evaluator
from evaluation_framework.core.gate_engine import GateEngine
from evaluation_framework.core.ports import EvaluationFrameworkRepository
from evaluation_framework.db.repository import SQLAlchemyEvaluationFrameworkRepository


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


async def get_repository(request: Request) -> AsyncIterator[EvaluationFrameworkRepository]:
    ctx: AppContext = request.app.state.ctx
    async with ctx.session_factory() as session:
        yield SQLAlchemyEvaluationFrameworkRepository(session)


def build_evaluator(ctx: AppContext, repository: EvaluationFrameworkRepository) -> Evaluator:
    return Evaluator(repository, ctx.llm_gateway, ctx.settings.gating.thresholds)


def build_gate_engine(repository: EvaluationFrameworkRepository) -> GateEngine:
    return GateEngine(repository)
