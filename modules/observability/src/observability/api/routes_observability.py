"""`/v1/observability/*` routes (LLD §3 "Platform-specific API surface").
The underlying `/v1/observability/ingest` endpoint is this module's own
addition, replacing the LLD's real OTLP ingestion endpoint — see
`core/ingestion.py`'s docstring.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from observability.api.deps import (
    build_alerting_service,
    build_completeness_calculator,
    build_cost_attribution_joiner,
    build_ingestion_service,
    build_reasoning_reconstructor,
    build_slo_service,
    get_ctx,
    get_repository,
)
from observability.app_context import AppContext
from observability.core.domain import (
    AlertComparison,
    AlertRuleNotFoundError,
    AlertStatus,
    SLOMetric,
    SLONotFoundError,
    TraceNotFoundError,
)
from observability.core.ports import ObservabilityRepository
from observability.schemas.observability import (
    AlertEventListResponse,
    AlertEventSchema,
    AlertRuleListResponse,
    AlertRuleSchema,
    CostAttributionEntrySchema,
    CostAttributionResponse,
    CreateAlertRuleRequest,
    CreateSLORequest,
    IngestRequest,
    IngestResponse,
    ReasoningNarrativeResponse,
    SLOEvaluationSchema,
    SLOListResponse,
    SLOSchema,
    SpanSchema,
    TraceCompletenessResponse,
    TraceDetailResponse,
    TraceListResponse,
    TraceSummarySchema,
)

router = APIRouter(prefix="/v1/observability", tags=["observability"])


def _reject_null_byte_query(**params: str | None) -> None:
    """A raw `Query()` string parameter never runs through a Pydantic
    body field's own NUL-byte validator -- a real CI run of a sibling
    module's contract tier (ticket #82) surfaced this exact bug class
    on a raw query parameter, an `UntranslatableCharacterError` at the
    database instead of a clean 422. Applied at the top of every route
    below taking a free-text (non-enum) query parameter."""
    for name, value in params.items():
        if value is not None and "\x00" in value:
            raise HTTPException(status_code=422, detail=f"{name} must not contain a NUL byte")


def _span_schema(span) -> SpanSchema:
    return SpanSchema(
        id=span.id, tenant_id=span.tenant_id, trace_id=span.trace_id, span_id=span.span_id,
        parent_span_id=span.parent_span_id, name=span.name, service_name=span.service_name,
        start_time=span.start_time, end_time=span.end_time, duration_seconds=span.duration_seconds,
        attributes=span.attributes, status=span.status, workflow_type=span.workflow_type,
    )


def _trace_summary_schema(summary) -> TraceSummarySchema:
    return TraceSummarySchema(
        trace_id=summary.trace_id, tenant_id=summary.tenant_id, workflow_type=summary.workflow_type,
        span_count=summary.span_count, start_time=summary.start_time, end_time=summary.end_time,
        duration_seconds=summary.duration_seconds, has_error=summary.has_error,
    )


def _slo_schema(slo) -> SLOSchema:
    return SLOSchema(
        id=slo.id, tenant_id=slo.tenant_id, name=slo.name, metric=slo.metric.value, target=slo.target,
        window_hours=slo.window_hours, service_name=slo.service_name, created_at=slo.created_at,
    )


def _alert_rule_schema(rule) -> AlertRuleSchema:
    return AlertRuleSchema(
        id=rule.id, tenant_id=rule.tenant_id, name=rule.name, metric=rule.metric.value,
        comparison=rule.comparison.value, threshold=rule.threshold, window_hours=rule.window_hours,
        service_name=rule.service_name, enabled=rule.enabled, created_at=rule.created_at,
    )


def _alert_event_schema(event) -> AlertEventSchema:
    return AlertEventSchema(
        id=event.id, rule_id=event.rule_id, tenant_id=event.tenant_id, status=event.status.value,
        value=event.value, threshold=event.threshold, triggered_at=event.triggered_at,
        resolved_at=event.resolved_at,
    )


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
    _reject_null_byte_query(tenant_id=tenant_id)
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
    _reject_null_byte_query(tenant_id=tenant_id)
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
    _reject_null_byte_query(tenant_id=tenant_id)
    calculator = build_completeness_calculator(ctx, repository)
    result = await calculator.compute(tenant_id)
    return TraceCompletenessResponse(
        tenant_id=result.tenant_id, completeness_ratio=result.completeness_ratio,
        traces_checked=result.traces_checked, traces_with_known_shape=result.traces_with_known_shape,
    )


# -- Trace query surface --

@router.get("/traces", response_model=TraceListResponse)
async def list_traces(
    tenant_id: str = Query(...),
    workflow_type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=1_000_000_000),
    repository: ObservabilityRepository = Depends(get_repository),
) -> TraceListResponse:
    _reject_null_byte_query(tenant_id=tenant_id, workflow_type=workflow_type)
    summaries, total = await repository.list_trace_summaries(
        tenant_id, workflow_type=workflow_type, limit=limit, offset=offset,
    )
    return TraceListResponse(
        items=[_trace_summary_schema(s) for s in summaries], total=total, limit=limit, offset=offset,
    )


@router.get("/traces/{trace_id}", response_model=TraceDetailResponse)
async def get_trace(
    trace_id: str,
    tenant_id: str = Query(...),
    repository: ObservabilityRepository = Depends(get_repository),
) -> TraceDetailResponse:
    _reject_null_byte_query(tenant_id=tenant_id)
    spans = await repository.list_spans_for_trace(tenant_id, trace_id)
    if not spans:
        raise HTTPException(status_code=404, detail=str(TraceNotFoundError(trace_id)))
    return TraceDetailResponse(trace_id=trace_id, tenant_id=tenant_id, spans=[_span_schema(s) for s in spans])


# -- SLOs --

@router.post("/slos", response_model=SLOSchema, status_code=201)
async def create_slo(
    body: CreateSLORequest,
    repository: ObservabilityRepository = Depends(get_repository),
) -> SLOSchema:
    service = build_slo_service(repository)
    slo = await service.create(
        tenant_id=body.tenant_id, name=body.name, metric=SLOMetric(body.metric), target=body.target,
        window_hours=body.window_hours, service_name=body.service_name,
    )
    return _slo_schema(slo)


@router.get("/slos", response_model=SLOListResponse)
async def list_slos(
    tenant_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=1_000_000_000),
    repository: ObservabilityRepository = Depends(get_repository),
) -> SLOListResponse:
    _reject_null_byte_query(tenant_id=tenant_id)
    service = build_slo_service(repository)
    slos, total = await service.list(tenant_id=tenant_id, limit=limit, offset=offset)
    return SLOListResponse(items=[_slo_schema(s) for s in slos], total=total, limit=limit, offset=offset)


@router.get("/slos/{slo_id}", response_model=SLOSchema)
async def get_slo(
    slo_id: str,
    repository: ObservabilityRepository = Depends(get_repository),
) -> SLOSchema:
    service = build_slo_service(repository)
    try:
        slo = await service.get(slo_id)
    except SLONotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _slo_schema(slo)


@router.post("/slos/{slo_id}/evaluate", response_model=SLOEvaluationSchema)
async def evaluate_slo(
    slo_id: str,
    repository: ObservabilityRepository = Depends(get_repository),
) -> SLOEvaluationSchema:
    service = build_slo_service(repository)
    try:
        result = await service.evaluate(slo_id)
    except SLONotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SLOEvaluationSchema(
        slo_id=result.slo_id, tenant_id=result.tenant_id, metric=result.metric.value, target=result.target,
        sample_count=result.sample_count, current_value=result.current_value, compliant=result.compliant,
        error_budget_remaining=result.error_budget_remaining, evaluated_at=result.evaluated_at,
    )


# -- Alerting --

@router.post("/alert-rules", response_model=AlertRuleSchema, status_code=201)
async def create_alert_rule(
    body: CreateAlertRuleRequest,
    repository: ObservabilityRepository = Depends(get_repository),
) -> AlertRuleSchema:
    service = build_alerting_service(repository)
    rule = await service.create_rule(
        tenant_id=body.tenant_id, name=body.name, metric=SLOMetric(body.metric),
        comparison=AlertComparison(body.comparison), threshold=body.threshold, window_hours=body.window_hours,
        service_name=body.service_name,
    )
    return _alert_rule_schema(rule)


@router.get("/alert-rules", response_model=AlertRuleListResponse)
async def list_alert_rules(
    tenant_id: str | None = Query(None),
    enabled: bool | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=1_000_000_000),
    repository: ObservabilityRepository = Depends(get_repository),
) -> AlertRuleListResponse:
    _reject_null_byte_query(tenant_id=tenant_id)
    service = build_alerting_service(repository)
    rules, total = await service.list_rules(tenant_id=tenant_id, enabled=enabled, limit=limit, offset=offset)
    return AlertRuleListResponse(items=[_alert_rule_schema(r) for r in rules], total=total, limit=limit, offset=offset)


@router.post("/alert-rules/{rule_id}/enable", response_model=AlertRuleSchema)
async def enable_alert_rule(
    rule_id: str,
    repository: ObservabilityRepository = Depends(get_repository),
) -> AlertRuleSchema:
    service = build_alerting_service(repository)
    try:
        rule = await service.set_enabled(rule_id, True)
    except AlertRuleNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _alert_rule_schema(rule)


@router.post("/alert-rules/{rule_id}/disable", response_model=AlertRuleSchema)
async def disable_alert_rule(
    rule_id: str,
    repository: ObservabilityRepository = Depends(get_repository),
) -> AlertRuleSchema:
    service = build_alerting_service(repository)
    try:
        rule = await service.set_enabled(rule_id, False)
    except AlertRuleNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _alert_rule_schema(rule)


@router.post("/alert-rules/{rule_id}/evaluate", response_model=AlertEventSchema | None)
async def evaluate_alert_rule(
    rule_id: str,
    repository: ObservabilityRepository = Depends(get_repository),
) -> AlertEventSchema | None:
    service = build_alerting_service(repository)
    try:
        event = await service.evaluate_rule(rule_id)
    except AlertRuleNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _alert_event_schema(event) if event is not None else None


@router.get("/alert-events", response_model=AlertEventListResponse)
async def list_alert_events(
    tenant_id: str | None = Query(None),
    status: AlertStatus | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=1_000_000_000),
    repository: ObservabilityRepository = Depends(get_repository),
) -> AlertEventListResponse:
    _reject_null_byte_query(tenant_id=tenant_id)
    events, total = await repository.list_alert_events(
        tenant_id=tenant_id, status=status, limit=limit, offset=offset,
    )
    return AlertEventListResponse(
        items=[_alert_event_schema(e) for e in events], total=total, limit=limit, offset=offset,
    )
