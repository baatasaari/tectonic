from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, Request

from billing_and_metering.app_context import AppContext
from billing_and_metering.core.invoice_service import InvoiceService
from billing_and_metering.core.metering_service import MeteringService
from billing_and_metering.core.ports import BillingRepository
from billing_and_metering.core.pricing_plan_service import PricingPlanService
from billing_and_metering.db.repository import SQLAlchemyBillingRepository


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


def resolve_tenant_id(request: Request, ctx: AppContext = Depends(get_ctx)) -> str:
    return request.headers.get("X-Tenant-Id", ctx.settings.tenant_id)


async def get_repository(ctx: AppContext = Depends(get_ctx)) -> AsyncIterator[BillingRepository]:
    async with ctx.session_factory() as session:
        yield SQLAlchemyBillingRepository(session)


def build_pricing_plan_service(repository: BillingRepository, ctx: AppContext | None = None) -> PricingPlanService:
    return PricingPlanService(repository, ctx.multi_tenancy if ctx is not None else None)


def build_metering_service(repository: BillingRepository, ctx: AppContext) -> MeteringService:
    return MeteringService(repository, ctx.finops, ctx.auditability)


def build_invoice_service(repository: BillingRepository, ctx: AppContext) -> InvoiceService:
    return InvoiceService(
        repository, build_pricing_plan_service(repository, ctx), build_metering_service(repository, ctx),
    )
