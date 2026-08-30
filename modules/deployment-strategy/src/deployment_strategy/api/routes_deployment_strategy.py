"""`/v1/deployment-strategy/*` routes (LLD §3)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from deployment_strategy.api.deps import (
    build_rollout_service,
    get_ctx,
    get_repository,
    resolve_tenant_id,
)
from deployment_strategy.app_context import AppContext
from deployment_strategy.core.domain import (
    CanaryHealthCheckFailedError,
    DeploymentNotFoundError,
    InvalidTransitionError,
    NoActiveDeploymentError,
)
from deployment_strategy.core.ports import DeploymentStrategyRepository
from deployment_strategy.schemas.deployment_strategy import (
    CanaryHealthResultSchema,
    DeploymentListResponse,
    DeploymentSchema,
    DeployRequest,
    RollbackRequest,
)

router = APIRouter(prefix="/v1/deployment-strategy", tags=["deployment-strategy"])


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


def _deployment_schema(deployment) -> DeploymentSchema:
    return DeploymentSchema(
        id=deployment.id, tenant_id=deployment.tenant_id, service_name=deployment.service_name,
        build_ref=deployment.build_ref, target=deployment.target, canary_percentage=deployment.canary_percentage,
        budget_policy_id=deployment.budget_policy_id, stage=deployment.stage.value, started_at=deployment.started_at,
        promoted_at=deployment.promoted_at, rolled_back_at=deployment.rolled_back_at,
        rollback_reason=deployment.rollback_reason, created_at=deployment.created_at, updated_at=deployment.updated_at,
    )


@router.post("/deployments", response_model=DeploymentSchema, status_code=201)
async def deploy(
    body: DeployRequest,
    tenant_id: str = Depends(resolve_tenant_id),
    ctx: AppContext = Depends(get_ctx),
    repository: DeploymentStrategyRepository = Depends(get_repository),
) -> DeploymentSchema:
    service = build_rollout_service(repository, ctx)
    deployment = await service.deploy(
        tenant_id=tenant_id, service_name=body.service_name, build_ref=body.build_ref, target=body.target,
        canary_percentage=body.canary_percentage, budget_policy_id=body.budget_policy_id,
    )
    return _deployment_schema(deployment)


@router.get("/deployments", response_model=DeploymentListResponse)
async def list_deployments(
    tenant_id: str | None = Query(None),
    service_name: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    repository: DeploymentStrategyRepository = Depends(get_repository),
) -> DeploymentListResponse:
    _reject_null_byte_query(tenant_id=tenant_id, service_name=service_name)
    deployments, total = await repository.list_deployments(
        tenant_id=tenant_id, service_name=service_name, limit=limit, offset=offset,
    )
    return DeploymentListResponse(
        items=[_deployment_schema(d) for d in deployments], total=total, limit=limit, offset=offset,
    )


@router.get("/deployments/{deployment_id}", response_model=DeploymentSchema)
async def get_deployment(
    deployment_id: str,
    repository: DeploymentStrategyRepository = Depends(get_repository),
) -> DeploymentSchema:
    deployment = await repository.get_deployment(deployment_id)
    if deployment is None:
        raise HTTPException(status_code=404, detail=str(DeploymentNotFoundError(deployment_id)))
    return _deployment_schema(deployment)


@router.get("/deployments/{deployment_id}/canary-health", response_model=CanaryHealthResultSchema)
async def canary_health(
    deployment_id: str,
    ctx: AppContext = Depends(get_ctx),
    repository: DeploymentStrategyRepository = Depends(get_repository),
) -> CanaryHealthResultSchema:
    service = build_rollout_service(repository, ctx)
    try:
        result = await service.canary_health(deployment_id)
    except DeploymentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return CanaryHealthResultSchema(
        groundedness_score=result.groundedness_score, cost_score=result.cost_score,
        composite_score=result.composite_score, passed=result.passed, reason=result.reason,
    )


@router.post("/deployments/{deployment_id}/promote", response_model=DeploymentSchema)
async def promote(
    deployment_id: str,
    ctx: AppContext = Depends(get_ctx),
    repository: DeploymentStrategyRepository = Depends(get_repository),
) -> DeploymentSchema:
    service = build_rollout_service(repository, ctx)
    try:
        deployment = await service.promote(deployment_id)
    except DeploymentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (InvalidTransitionError, CanaryHealthCheckFailedError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _deployment_schema(deployment)


@router.post("/deployments/{deployment_id}/rollback", response_model=DeploymentSchema)
async def rollback(
    deployment_id: str,
    body: RollbackRequest,
    ctx: AppContext = Depends(get_ctx),
    repository: DeploymentStrategyRepository = Depends(get_repository),
) -> DeploymentSchema:
    service = build_rollout_service(repository, ctx)
    try:
        deployment = await service.rollback(deployment_id, reason=body.reason)
    except DeploymentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _deployment_schema(deployment)


@router.get("/services/{service_name}/active", response_model=DeploymentSchema)
async def get_active_deployment(
    service_name: str,
    target: str = Query(...),
    tenant_id: str = Depends(resolve_tenant_id),
    ctx: AppContext = Depends(get_ctx),
    repository: DeploymentStrategyRepository = Depends(get_repository),
) -> DeploymentSchema:
    service = build_rollout_service(repository, ctx)
    try:
        deployment = await service.get_active_deployment(tenant_id=tenant_id, service_name=service_name, target=target)
    except NoActiveDeploymentError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _deployment_schema(deployment)
