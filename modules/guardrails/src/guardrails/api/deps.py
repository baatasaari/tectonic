from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request

from guardrails.app_context import AppContext
from guardrails.core.policy_engine import PolicyEngine
from guardrails.core.ports import GuardrailsRepository
from guardrails.core.red_team import RedTeamRunner
from guardrails.db.repository import SQLAlchemyGuardrailsRepository


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


async def get_repository(request: Request) -> AsyncIterator[GuardrailsRepository]:
    ctx: AppContext = request.app.state.ctx
    async with ctx.session_factory() as session:
        yield SQLAlchemyGuardrailsRepository(session)


def build_policy_engine(ctx: AppContext) -> PolicyEngine:
    return PolicyEngine(ctx.llm_gateway)


def build_red_team_runner(ctx: AppContext, repository: GuardrailsRepository) -> RedTeamRunner:
    policy_engine = build_policy_engine(ctx)
    return RedTeamRunner(
        repository, policy_engine, ctx.llm_gateway, ctx.sentinel_agents, ctx.settings.red_team.attempts_per_run,
    )
