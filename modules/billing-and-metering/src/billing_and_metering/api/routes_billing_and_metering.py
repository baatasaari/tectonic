"""`/v1/billing/*` routes (LLD §3)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query


def _reject_null_byte_query(**params: str | None) -> None:
    """A raw `Query()` string parameter never runs through a Pydantic
    body field's own NUL-byte validator (see e.g. Multi-tenancy's own
    `_reject_null_byte` in schemas/multi_tenancy.py) -- a real CI run of
    a sibling module's contract tier (ticket #82) surfaced this exact
    bug class on a raw query parameter, an `UntranslatableCharacterError`
    at the database instead of a clean 422. Applied at the top of every
    route below taking a free-text (non-enum) query parameter."""
    for name, value in params.items():
        if value is not None and "\x00" in value:
            raise HTTPException(status_code=422, detail=f"{name} must not contain a NUL byte")

from billing_and_metering.api.deps import (
    build_invoice_service,
    build_metering_service,
    build_pricing_plan_service,
    get_ctx,
    get_repository,
)
from billing_and_metering.app_context import AppContext
from billing_and_metering.core.domain import (
    InvalidTransitionError,
    InvoiceNotFoundError,
    InvoiceStatus,
    PricingPlanNotFoundError,
)
from billing_and_metering.core.ports import BillingRepository
from billing_and_metering.schemas.billing_and_metering import (
    CreatePricingPlanRequest,
    GeneratedInvoiceSchema,
    GenerateInvoiceRequest,
    InvoiceLineSchema,
    InvoiceListResponse,
    InvoiceSchema,
    MeterTenantResponse,
    PricingPlanListResponse,
    PricingPlanSchema,
    UsageRecordListResponse,
    UsageRecordSchema,
)

router = APIRouter(prefix="/v1/billing", tags=["billing"])


def _plan_schema(plan) -> PricingPlanSchema:
    return PricingPlanSchema(
        id=plan.id, tenant_id=plan.tenant_id, name=plan.name, unit_prices=plan.unit_prices,
        created_at=plan.created_at,
    )


def _invoice_schema(invoice) -> InvoiceSchema:
    return InvoiceSchema(
        id=invoice.id, tenant_id=invoice.tenant_id, period=invoice.period, status=invoice.status.value,
        total_amount=invoice.total_amount, complete=invoice.complete, generated_at=invoice.generated_at,
        finalized_at=invoice.finalized_at,
    )


def _line_schema(line) -> InvoiceLineSchema:
    return InvoiceLineSchema(
        id=line.id, invoice_id=line.invoice_id, resource=line.resource, quantity=line.quantity,
        unit_price=line.unit_price, amount=line.amount,
    )


def _usage_schema(record) -> UsageRecordSchema:
    return UsageRecordSchema(
        id=record.id, tenant_id=record.tenant_id, period=record.period, resource=record.resource,
        quantity=record.quantity, source=record.source, computed_at=record.computed_at,
    )


@router.post("/pricing-plans", response_model=PricingPlanSchema, status_code=201)
async def create_pricing_plan(
    body: CreatePricingPlanRequest,
    ctx: AppContext = Depends(get_ctx),
    repository: BillingRepository = Depends(get_repository),
) -> PricingPlanSchema:
    service = build_pricing_plan_service(repository, ctx)
    plan = await service.create(tenant_id=body.tenant_id, name=body.name, unit_prices=body.unit_prices)
    return _plan_schema(plan)


@router.get("/pricing-plans", response_model=PricingPlanListResponse)
async def list_pricing_plans(
    tenant_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=1_000_000_000),
    repository: BillingRepository = Depends(get_repository),
) -> PricingPlanListResponse:
    _reject_null_byte_query(tenant_id=tenant_id)
    service = build_pricing_plan_service(repository)
    plans, total = await service.list(tenant_id=tenant_id, limit=limit, offset=offset)
    return PricingPlanListResponse(items=[_plan_schema(p) for p in plans], total=total, limit=limit, offset=offset)


@router.get("/pricing-plans/{plan_id}", response_model=PricingPlanSchema)
async def get_pricing_plan(
    plan_id: str,
    repository: BillingRepository = Depends(get_repository),
) -> PricingPlanSchema:
    service = build_pricing_plan_service(repository)
    plan = await service.get(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"Pricing plan not found: {plan_id}")
    return _plan_schema(plan)


@router.post("/invoices/generate", response_model=GeneratedInvoiceSchema, status_code=201)
async def generate_invoice(
    body: GenerateInvoiceRequest,
    ctx: AppContext = Depends(get_ctx),
    repository: BillingRepository = Depends(get_repository),
) -> GeneratedInvoiceSchema:
    service = build_invoice_service(repository, ctx)
    try:
        generated = await service.generate_invoice(tenant_id=body.tenant_id, period=body.period)
    except PricingPlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return GeneratedInvoiceSchema(
        invoice=_invoice_schema(generated.invoice), lines=[_line_schema(line) for line in generated.lines],
    )


@router.get("/invoices", response_model=InvoiceListResponse)
async def list_invoices(
    tenant_id: str | None = Query(None),
    status: InvoiceStatus | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=1_000_000_000),
    ctx: AppContext = Depends(get_ctx),
    repository: BillingRepository = Depends(get_repository),
) -> InvoiceListResponse:
    _reject_null_byte_query(tenant_id=tenant_id)
    service = build_invoice_service(repository, ctx)
    # Query(...) typed as InvoiceStatus | None: FastAPI/Pydantic validates and coerces it
    # itself, rejecting anything not a real InvoiceStatus value with a clean 422 -- this
    # used to accept an arbitrary str and call InvoiceStatus(status) by hand, which raised
    # an unhandled ValueError (500) for any non-member string (caught by the contract-test
    # tier in tests/contract/).
    invoices, total = await service.list_invoices(tenant_id=tenant_id, status=status, limit=limit, offset=offset)
    return InvoiceListResponse(items=[_invoice_schema(i) for i in invoices], total=total, limit=limit, offset=offset)


@router.get("/invoices/{invoice_id}", response_model=GeneratedInvoiceSchema)
async def get_invoice(
    invoice_id: str,
    ctx: AppContext = Depends(get_ctx),
    repository: BillingRepository = Depends(get_repository),
) -> GeneratedInvoiceSchema:
    service = build_invoice_service(repository, ctx)
    try:
        generated = await service.get_invoice(invoice_id)
    except InvoiceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return GeneratedInvoiceSchema(
        invoice=_invoice_schema(generated.invoice), lines=[_line_schema(line) for line in generated.lines],
    )


@router.post("/invoices/{invoice_id}/finalize", response_model=InvoiceSchema)
async def finalize_invoice(
    invoice_id: str,
    ctx: AppContext = Depends(get_ctx),
    repository: BillingRepository = Depends(get_repository),
) -> InvoiceSchema:
    service = build_invoice_service(repository, ctx)
    try:
        invoice = await service.finalize(invoice_id)
    except InvoiceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _invoice_schema(invoice)


@router.post("/tenants/{tenant_id}/meter", response_model=MeterTenantResponse)
async def meter_tenant(
    tenant_id: str,
    period: str = Query(..., description="'daily' or 'monthly', matching the tenant's pricing plan's own period"),
    ctx: AppContext = Depends(get_ctx),
    repository: BillingRepository = Depends(get_repository),
) -> MeterTenantResponse:
    """Real HTTP trigger for `MeteringService.meter_tenant()` -- see
    MeterTenantResponse's own docstring (ticket #82) for why this didn't
    already exist. A real deployment's scheduler calls this periodically;
    this endpoint is that real, tested computation exposed in the meantime."""
    plan = await repository.get_pricing_plan_for_tenant(tenant_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"no pricing plan for tenant '{tenant_id}'")

    service = build_metering_service(repository, ctx)
    records, complete = await service.meter_tenant(tenant_id=tenant_id, period=period, plan=plan)
    return MeterTenantResponse(
        tenant_id=tenant_id, period=period, complete=complete,
        records=[_usage_schema(r) for r in records],
    )


@router.get("/usage-records", response_model=UsageRecordListResponse)
async def list_usage_records(
    tenant_id: str | None = Query(None),
    period: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=1_000_000_000),
    repository: BillingRepository = Depends(get_repository),
) -> UsageRecordListResponse:
    _reject_null_byte_query(tenant_id=tenant_id, period=period)
    records, total = await repository.list_usage_records(tenant_id=tenant_id, period=period, limit=limit, offset=offset)
    return UsageRecordListResponse(items=[_usage_schema(r) for r in records], total=total, limit=limit, offset=offset)
