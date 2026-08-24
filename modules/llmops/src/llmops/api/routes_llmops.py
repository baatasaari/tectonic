"""`/v1/llmops/*` routes (LLD §3)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from llmops.api.deps import (
    build_model_registry_service,
    build_rollout_service,
    get_ctx,
    get_repository,
    resolve_tenant_id,
)
from llmops.app_context import AppContext
from llmops.core.domain import (
    CanaryGateFailedError,
    DeploymentNotFoundError,
    InvalidTransitionError,
    ModelVersionNotFoundError,
    NoActiveVersionError,
)
from llmops.core.ports import LLMOpsRepository
from llmops.schemas.llmops import (
    CanaryGateResultSchema,
    DeploymentSchema,
    ModelVersionListResponse,
    ModelVersionSchema,
    RegisterModelVersionRequest,
    RollbackRequest,
    StartCanaryRequest,
)

router = APIRouter(prefix="/v1/llmops", tags=["llmops"])


def _version_schema(version) -> ModelVersionSchema:
    return ModelVersionSchema(
        id=version.id, tenant_id=version.tenant_id, model_name=version.model_name, version=version.version,
        artifact_ref=version.artifact_ref, status=version.status.value, created_at=version.created_at,
    )


def _deployment_schema(deployment) -> DeploymentSchema:
    return DeploymentSchema(
        id=deployment.id, tenant_id=deployment.tenant_id, model_version_id=deployment.model_version_id,
        model_name=deployment.model_name, target=deployment.target, canary_percentage=deployment.canary_percentage,
        stage=deployment.stage.value, started_at=deployment.started_at, promoted_at=deployment.promoted_at,
        rolled_back_at=deployment.rolled_back_at, rollback_reason=deployment.rollback_reason,
        created_at=deployment.created_at, updated_at=deployment.updated_at,
    )


@router.post("/model-versions", response_model=ModelVersionSchema, status_code=201)
async def register_model_version(
    body: RegisterModelVersionRequest,
    tenant_id: str = Depends(resolve_tenant_id),
    repository: LLMOpsRepository = Depends(get_repository),
) -> ModelVersionSchema:
    service = build_model_registry_service(repository)
    version = await service.register(
        tenant_id=tenant_id, model_name=body.model_name, version=body.version, artifact_ref=body.artifact_ref,
    )
    return _version_schema(version)


@router.get("/model-versions", response_model=ModelVersionListResponse)
async def list_model_versions(
    tenant_id: str | None = Query(None),
    model_name: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    repository: LLMOpsRepository = Depends(get_repository),
) -> ModelVersionListResponse:
    service = build_model_registry_service(repository)
    versions, total = await service.list(tenant_id=tenant_id, model_name=model_name, limit=limit, offset=offset)
    return ModelVersionListResponse(items=[_version_schema(v) for v in versions], total=total, limit=limit, offset=offset)


@router.get("/model-versions/{model_version_id}", response_model=ModelVersionSchema)
async def get_model_version(
    model_version_id: str,
    repository: LLMOpsRepository = Depends(get_repository),
) -> ModelVersionSchema:
    service = build_model_registry_service(repository)
    try:
        version = await service.get(model_version_id)
    except ModelVersionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _version_schema(version)


@router.post("/deployments", response_model=DeploymentSchema, status_code=201)
async def start_canary(
    body: StartCanaryRequest,
    tenant_id: str = Depends(resolve_tenant_id),
    ctx: AppContext = Depends(get_ctx),
    repository: LLMOpsRepository = Depends(get_repository),
) -> DeploymentSchema:
    service = build_rollout_service(repository, ctx)
    try:
        deployment = await service.start_canary(
            tenant_id=tenant_id, model_version_id=body.model_version_id, target=body.target,
            canary_percentage=body.canary_percentage,
        )
    except ModelVersionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _deployment_schema(deployment)


@router.get("/deployments/{deployment_id}", response_model=DeploymentSchema)
async def get_deployment(
    deployment_id: str,
    repository: LLMOpsRepository = Depends(get_repository),
) -> DeploymentSchema:
    deployment = await repository.get_deployment(deployment_id)
    if deployment is None:
        raise HTTPException(status_code=404, detail=str(DeploymentNotFoundError(deployment_id)))
    return _deployment_schema(deployment)


@router.get("/deployments/{deployment_id}/canary-gate", response_model=CanaryGateResultSchema)
async def canary_gate(
    deployment_id: str,
    ctx: AppContext = Depends(get_ctx),
    repository: LLMOpsRepository = Depends(get_repository),
) -> CanaryGateResultSchema:
    service = build_rollout_service(repository, ctx)
    try:
        result = await service.canary_gate(deployment_id)
    except (DeploymentNotFoundError, ModelVersionNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return CanaryGateResultSchema(
        sample_size=result.sample_size, pass_rate=result.pass_rate, passed=result.passed, reason=result.reason,
    )


@router.post("/deployments/{deployment_id}/promote", response_model=DeploymentSchema)
async def promote(
    deployment_id: str,
    ctx: AppContext = Depends(get_ctx),
    repository: LLMOpsRepository = Depends(get_repository),
) -> DeploymentSchema:
    service = build_rollout_service(repository, ctx)
    try:
        deployment = await service.promote(deployment_id)
    except (DeploymentNotFoundError, ModelVersionNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (InvalidTransitionError, CanaryGateFailedError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _deployment_schema(deployment)


@router.post("/deployments/{deployment_id}/rollback", response_model=DeploymentSchema)
async def rollback(
    deployment_id: str,
    body: RollbackRequest,
    ctx: AppContext = Depends(get_ctx),
    repository: LLMOpsRepository = Depends(get_repository),
) -> DeploymentSchema:
    service = build_rollout_service(repository, ctx)
    try:
        deployment = await service.rollback(deployment_id, reason=body.reason)
    except DeploymentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _deployment_schema(deployment)


@router.get("/models/{model_name}/active", response_model=ModelVersionSchema)
async def get_active_version(
    model_name: str,
    target: str = Query(...),
    tenant_id: str = Depends(resolve_tenant_id),
    ctx: AppContext = Depends(get_ctx),
    repository: LLMOpsRepository = Depends(get_repository),
) -> ModelVersionSchema:
    service = build_rollout_service(repository, ctx)
    try:
        version = await service.get_active_version(tenant_id=tenant_id, model_name=model_name, target=target)
    except NoActiveVersionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _version_schema(version)
