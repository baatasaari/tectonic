"""`/v1/observability/*` routes (LLD §3 "Platform-specific API surface").
The underlying `/v1/observability/ingest` endpoint is this module's own
addition, replacing the LLD's real OTLP ingestion endpoint — see
`core/ingestion.py`'s docstring.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from observability.api.deps import (
    build_completeness_calculator,
    build_cost_attribution_joiner,
    build_ingestion_service,
    build_reasoning_reconstructor,
    get_ctx,
    get_repository,
)
from observability.app_context import AppContext
from observability.core.domain import TraceNotFoundError
from observability.core.ports import ObservabilityRepository
from observability.schemas.observability import (
    CostAttributionEntrySchema,
    CostAttributionResponse,
    IngestRequest,
    IngestResponse,
    ReasoningNarrativeResponse,
    TraceCompletenessResponse,
)

router = APIRouter(prefix="/v1/observability", tags=["observability"])


@router.post("/ingest", response_model=IngestResponse, status_code=201)
async def ingest(
    body: IngestRequest,
    repository: ObservabilityRepository = Depends(get_repository),
) -> IngestResponse:
    service = build_ingestion_service(repository)
    count = await service.ingest(body.tenant_id, body.trace_id, [s.model_dump() for s in body.spans], body.workflow_type)
    return IngestResponse(trace_id=body.trace_id, spans_ingested=count)


@router.get("/reasoning-narrative/{trace_id}", response_model=ReasoningNarrativeResponse)
async def reasoning_narrative(
    trace_id: str,
    tenant_id: str = Query(...),
    ctx: AppContext = Depends(get_ctx),
    repository: ObservabilityRepository = Depends(get_repository),
) -> ReasoningNarrativeResponse:
    spans = await repository.list_spans_for_trace(tenant_id, trace_id)
    if not spans:
        raise HTTPException(status_code=404, detail=str(TraceNotFoundError(trace_id)))

    reconstructor = build_reasoning_reconstructor(ctx)
    narrative = await reconstructor.reconstruct(spans)
    return ReasoningNarrativeResponse(trace_id=trace_id, narrative=narrative, span_count=len(spans))


@router.get("/cost-attribution/{trace_id}", response_model=CostAttributionResponse)
async def cost_attribution(
    trace_id: str,
    tenant_id: str = Query(...),
    repository: ObservabilityRepository = Depends(get_repository),
) -> CostAttributionResponse:
    spans = await repository.list_spans_for_trace(tenant_id, trace_id)
    if not spans:
        raise HTTPException(status_code=404, detail=str(TraceNotFoundError(trace_id)))

    joiner = build_cost_attribution_joiner()
    entries = joiner.join(spans)
    return CostAttributionResponse(
        trace_id=trace_id,
        entries=[
            CostAttributionEntrySchema(
                span_id=e.span_id, name=e.name, duration_seconds=e.duration_seconds, input_tokens=e.input_tokens,
                output_tokens=e.output_tokens, cost_usd=e.cost_usd,
            )
            for e in entries
        ],
        total_cost_usd=joiner.total_cost(entries),
    )


@router.get("/trace-completeness", response_model=TraceCompletenessResponse)
async def trace_completeness(
    tenant_id: str = Query(...),
    ctx: AppContext = Depends(get_ctx),
    repository: ObservabilityRepository = Depends(get_repository),
) -> TraceCompletenessResponse:
    calculator = build_completeness_calculator(ctx, repository)
    result = await calculator.compute(tenant_id)
    return TraceCompletenessResponse(
        tenant_id=result.tenant_id, completeness_ratio=result.completeness_ratio,
        traces_checked=result.traces_checked, traces_with_known_shape=result.traces_with_known_shape,
    )
