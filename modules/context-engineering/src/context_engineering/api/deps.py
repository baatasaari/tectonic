from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request

from context_engineering.app_context import AppContext
from context_engineering.core.compression import CompressionService
from context_engineering.core.context_assembly_service import ContextAssemblyService
from context_engineering.core.ontology_filter import OntologyFilter
from context_engineering.core.ports import ContextRepository
from context_engineering.core.prioritisation_engine import PrioritisationEngine
from context_engineering.core.token_budget_enforcer import TokenBudgetEnforcer
from context_engineering.db.repository import SQLAlchemyContextRepository


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


async def get_repository(request: Request) -> AsyncIterator[ContextRepository]:
    ctx: AppContext = request.app.state.ctx
    async with ctx.session_factory() as session:
        yield SQLAlchemyContextRepository(session)


def build_assembly_service(ctx: AppContext, repository: ContextRepository) -> ContextAssemblyService:
    return ContextAssemblyService(
        repository=repository,
        ontology_filter=OntologyFilter(),
        prioritisation_engine=PrioritisationEngine(),
        budget_enforcer=TokenBudgetEnforcer(ctx.token_counter),
        compression_service=CompressionService(ctx.llm_gateway, ctx.token_counter),
        prioritisation_config=ctx.settings.prioritisation,
        budget_config=ctx.settings.budget,
    )
