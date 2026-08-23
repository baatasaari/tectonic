from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request

from regulatory_compliance.app_context import AppContext
from regulatory_compliance.core.crosswalk_engine import CoverageCalculator, CrosswalkEngine
from regulatory_compliance.core.evidence_generator import EvidencePackGenerator
from regulatory_compliance.core.ports import RegulatoryComplianceRepository
from regulatory_compliance.core.regulatory_feed import RegulatoryFeedManager
from regulatory_compliance.db.repository import SQLAlchemyRegulatoryComplianceRepository


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


async def get_repository(request: Request) -> AsyncIterator[RegulatoryComplianceRepository]:
    ctx: AppContext = request.app.state.ctx
    async with ctx.session_factory() as session:
        yield SQLAlchemyRegulatoryComplianceRepository(session)


def build_crosswalk_engine(repository: RegulatoryComplianceRepository) -> CrosswalkEngine:
    return CrosswalkEngine(repository)


def build_coverage_calculator(repository: RegulatoryComplianceRepository) -> CoverageCalculator:
    return CoverageCalculator(repository)


def build_evidence_generator(ctx: AppContext, repository: RegulatoryComplianceRepository) -> EvidencePackGenerator:
    return EvidencePackGenerator(repository, ctx.auditability, ctx.settings.evidence.output_format)


def build_feed_manager(repository: RegulatoryComplianceRepository) -> RegulatoryFeedManager:
    return RegulatoryFeedManager(repository)


async def run_evidence_generation(ctx: AppContext, pack_id: str, tenant_id: str, framework_name: str) -> None:
    """Runs as a FastAPI `BackgroundTasks` job — opens its own session rather than reusing
    the request-scoped one, since that session is already closed (its `yield` dependency
    torn down) by the time background tasks execute after the response is sent."""
    async with ctx.session_factory() as session:
        repository = SQLAlchemyRegulatoryComplianceRepository(session)
        generator = build_evidence_generator(ctx, repository)
        await generator.generate(pack_id, tenant_id, framework_name)
