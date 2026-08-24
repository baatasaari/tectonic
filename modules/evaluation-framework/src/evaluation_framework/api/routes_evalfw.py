"""`/v1/evaluation-framework/*` routes (LLD §3)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from evaluation_framework.api.deps import (
    build_evaluator,
    build_gate_engine,
    get_ctx,
    get_repository,
)
from evaluation_framework.app_context import AppContext
from evaluation_framework.core.domain import DomainMetricPackRecord, EvalRunNotFoundError, new_id
from evaluation_framework.core.ports import EvaluationFrameworkRepository
from evaluation_framework.schemas.evalfw import (
    CreateDomainPackRequest,
    DomainMetricPackSchema,
    EvalRunSchema,
    EvaluateRequest,
    GateRequest,
    GateResultSchema,
    MetricScoreListResponse,
    MetricScoreSchema,
    SampleRequest,
    SampleResponse,
)

router = APIRouter(prefix="/v1/evaluation-framework", tags=["evaluation-framework"])


def _score_schema(s) -> MetricScoreSchema:
    return MetricScoreSchema(id=s.id, metric_name=s.metric_name, score=s.score, threshold=s.threshold, passed=s.passed, created_at=s.created_at)


def _run_schema(run, scores) -> EvalRunSchema:
    return EvalRunSchema(
        id=run.id, tenant_id=run.tenant_id, trigger_source=run.trigger_source, agent_ref=run.agent_ref,
        metrics_evaluated=run.metrics_evaluated, status=run.status.value, started_at=run.started_at,
        completed_at=run.completed_at, scores=[_score_schema(s) for s in scores],
    )


async def _merged_thresholds(repository: EvaluationFrameworkRepository, tenant_id: str) -> dict[str, float]:
    packs = await repository.list_domain_packs(tenant_id)
    merged: dict[str, float] = {}
    for pack in packs:
        if pack.enabled:
            merged.update(pack.custom_thresholds)
    return merged


@router.post("/evaluate", response_model=EvalRunSchema, status_code=201)
async def evaluate(
    body: EvaluateRequest,
    ctx: AppContext = Depends(get_ctx),
    repository: EvaluationFrameworkRepository = Depends(get_repository),
) -> EvalRunSchema:
    evaluator = build_evaluator(ctx, repository)
    custom_thresholds = await _merged_thresholds(repository, body.tenant_id)
    run, scores = await evaluator.evaluate(
        body.tenant_id, body.agent_ref, body.agent_output, body.reference_data, body.metric_set, body.trigger_source,
        custom_thresholds=custom_thresholds,
    )
    return _run_schema(run, scores)


@router.post("/gate", response_model=GateResultSchema)
async def gate(
    body: GateRequest,
    repository: EvaluationFrameworkRepository = Depends(get_repository),
) -> GateResultSchema:
    engine = build_gate_engine(repository)
    try:
        result = await engine.gate(body.tenant_id, body.eval_run_id, body.environment)
    except EvalRunNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return GateResultSchema(
        id=result.id, eval_run_id=result.eval_run_id, overall_passed=result.overall_passed,
        blocking_failures=result.blocking_failures, environment=result.environment, created_at=result.created_at,
    )


@router.post("/domain-packs", response_model=DomainMetricPackSchema, status_code=201)
async def create_domain_pack(
    body: CreateDomainPackRequest,
    repository: EvaluationFrameworkRepository = Depends(get_repository),
) -> DomainMetricPackSchema:
    record = DomainMetricPackRecord(
        id=new_id(), tenant_id=body.tenant_id, pack_name=body.pack_name, custom_thresholds=body.custom_thresholds,
    )
    record = await repository.create_domain_pack(record)
    return DomainMetricPackSchema(
        id=record.id, tenant_id=record.tenant_id, pack_name=record.pack_name, enabled=record.enabled,
        custom_thresholds=record.custom_thresholds,
    )


@router.get("/scores", response_model=MetricScoreListResponse)
async def list_scores(
    tenant_id: str,
    agent_ref: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    repository: EvaluationFrameworkRepository = Depends(get_repository),
) -> MetricScoreListResponse:
    scores, total = await repository.list_metric_scores_for_tenant(
        tenant_id, agent_ref=agent_ref, limit=limit, offset=offset,
    )
    return MetricScoreListResponse(
        items=[_score_schema(s) for s in scores], total=total, limit=limit, offset=offset,
    )


@router.post("/sample", response_model=SampleResponse)
async def sample(
    body: SampleRequest,
    ctx: AppContext = Depends(get_ctx),
    repository: EvaluationFrameworkRepository = Depends(get_repository),
) -> SampleResponse:
    if not ctx.settings.production_sampling.enabled or not ctx.sampler.should_sample(body.interaction_id):
        return SampleResponse(sampled=False)

    evaluator = build_evaluator(ctx, repository)
    custom_thresholds = await _merged_thresholds(repository, body.tenant_id)
    run, _scores = await evaluator.evaluate(
        body.tenant_id, body.agent_ref, body.agent_output, body.reference_data, body.metric_set,
        "production_sample", custom_thresholds=custom_thresholds,
    )
    return SampleResponse(sampled=True, eval_run_id=run.id)
