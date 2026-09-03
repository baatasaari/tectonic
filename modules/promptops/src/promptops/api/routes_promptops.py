"""`/v1/promptops/*` routes (LLD §3)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from promptops.api.deps import (
    build_ab_testing_service,
    build_drift_detection_service,
    build_prompt_registry_service,
    build_reflection_optimiser,
    get_ctx,
    get_repository,
    resolve_tenant_id,
)
from promptops.app_context import AppContext
from promptops.core.domain import (
    ABTestNotConclusiveError,
    ABTestNotFoundError,
    EvaluationGateFailedError,
    InvalidTransitionError,
    NoActivePromptVersionError,
    PromptVersionNotFoundError,
)
from promptops.core.ports import PromptOpsRepository
from promptops.schemas.promptops import (
    ABTestResultSchema,
    ABTestSchema,
    DriftCheckResultSchema,
    PromptVersionListResponse,
    PromptVersionSchema,
    RegisterPromptVersionRequest,
    StartABTestRequest,
)

router = APIRouter(prefix="/v1/promptops", tags=["promptops"])


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


def _version_schema(version) -> PromptVersionSchema:
    return PromptVersionSchema(
        id=version.id, tenant_id=version.tenant_id, prompt_name=version.prompt_name, version=version.version,
        template=version.template, status=version.status.value, parent_version_id=version.parent_version_id,
        promoted_pass_rate=version.promoted_pass_rate, promoted_sample_size=version.promoted_sample_size,
        created_at=version.created_at, updated_at=version.updated_at,
    )


def _ab_test_schema(ab_test) -> ABTestSchema:
    return ABTestSchema(
        id=ab_test.id, tenant_id=ab_test.tenant_id, prompt_name=ab_test.prompt_name,
        version_a_id=ab_test.version_a_id, version_b_id=ab_test.version_b_id, status=ab_test.status.value,
        winner_version_id=ab_test.winner_version_id, p_value=ab_test.p_value, sample_size_a=ab_test.sample_size_a,
        sample_size_b=ab_test.sample_size_b, started_at=ab_test.started_at, concluded_at=ab_test.concluded_at,
    )


@router.post("/prompt-versions", response_model=PromptVersionSchema, status_code=201)
async def register_prompt_version(
    body: RegisterPromptVersionRequest,
    tenant_id: str = Depends(resolve_tenant_id),
    repository: PromptOpsRepository = Depends(get_repository),
) -> PromptVersionSchema:
    service = build_prompt_registry_service(repository)
    version = await service.register(
        tenant_id=tenant_id, prompt_name=body.prompt_name, version=body.version, template=body.template,
    )
    return _version_schema(version)


@router.get("/prompt-versions", response_model=PromptVersionListResponse)
async def list_prompt_versions(
    tenant_id: str | None = Query(None),
    prompt_name: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=1_000_000_000),
    repository: PromptOpsRepository = Depends(get_repository),
) -> PromptVersionListResponse:
    _reject_null_byte_query(tenant_id=tenant_id, prompt_name=prompt_name)
    service = build_prompt_registry_service(repository)
    versions, total = await service.list(tenant_id=tenant_id, prompt_name=prompt_name, limit=limit, offset=offset)
    return PromptVersionListResponse(
        items=[_version_schema(v) for v in versions], total=total, limit=limit, offset=offset,
    )


@router.get("/prompt-versions/{prompt_version_id}", response_model=PromptVersionSchema)
async def get_prompt_version(
    prompt_version_id: str,
    repository: PromptOpsRepository = Depends(get_repository),
) -> PromptVersionSchema:
    service = build_prompt_registry_service(repository)
    try:
        version = await service.get(prompt_version_id)
    except PromptVersionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _version_schema(version)


@router.get("/prompt-versions/{prompt_version_id}/drift-check", response_model=DriftCheckResultSchema)
async def drift_check(
    prompt_version_id: str,
    ctx: AppContext = Depends(get_ctx),
    repository: PromptOpsRepository = Depends(get_repository),
) -> DriftCheckResultSchema:
    service = build_drift_detection_service(repository, ctx)
    try:
        result = await service.check(prompt_version_id)
    except PromptVersionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return DriftCheckResultSchema(
        baseline_pass_rate=result.baseline_pass_rate, current_pass_rate=result.current_pass_rate,
        current_sample_size=result.current_sample_size, p_value=result.p_value, drifted=result.drifted,
        reason=result.reason,
    )


@router.post("/prompt-versions/{prompt_version_id}/reflect", response_model=PromptVersionSchema | None)
async def reflect(
    prompt_version_id: str,
    response: Response,
    ctx: AppContext = Depends(get_ctx),
    repository: PromptOpsRepository = Depends(get_repository),
) -> PromptVersionSchema | None:
    optimiser = build_reflection_optimiser(repository, ctx)
    try:
        new_version = await optimiser.propose(prompt_version_id)
    except PromptVersionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if new_version is None:
        response.status_code = 204
        return None
    response.status_code = 201
    return _version_schema(new_version)


@router.post("/ab-tests", response_model=ABTestSchema, status_code=201)
async def start_ab_test(
    body: StartABTestRequest,
    tenant_id: str = Depends(resolve_tenant_id),
    ctx: AppContext = Depends(get_ctx),
    repository: PromptOpsRepository = Depends(get_repository),
) -> ABTestSchema:
    service = build_ab_testing_service(repository, ctx)
    try:
        ab_test = await service.start(
            tenant_id=tenant_id, prompt_name=body.prompt_name, version_a_id=body.version_a_id,
            version_b_id=body.version_b_id,
        )
    except PromptVersionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _ab_test_schema(ab_test)


@router.get("/ab-tests/{ab_test_id}", response_model=ABTestSchema)
async def get_ab_test(
    ab_test_id: str,
    repository: PromptOpsRepository = Depends(get_repository),
) -> ABTestSchema:
    ab_test = await repository.get_ab_test(ab_test_id)
    if ab_test is None:
        raise HTTPException(status_code=404, detail=str(ABTestNotFoundError(ab_test_id)))
    return _ab_test_schema(ab_test)


@router.get("/ab-tests/{ab_test_id}/result", response_model=ABTestResultSchema)
async def ab_test_result(
    ab_test_id: str,
    ctx: AppContext = Depends(get_ctx),
    repository: PromptOpsRepository = Depends(get_repository),
) -> ABTestResultSchema:
    service = build_ab_testing_service(repository, ctx)
    try:
        result = await service.evaluate(ab_test_id)
    except (ABTestNotFoundError, PromptVersionNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ABTestResultSchema(
        sample_size_a=result.sample_size_a, sample_size_b=result.sample_size_b, pass_rate_a=result.pass_rate_a,
        pass_rate_b=result.pass_rate_b, p_value=result.p_value, significant=result.significant,
        winner_version_id=result.winner_version_id, reason=result.reason,
    )


@router.post("/ab-tests/{ab_test_id}/conclude", response_model=ABTestSchema)
async def conclude_ab_test(
    ab_test_id: str,
    ctx: AppContext = Depends(get_ctx),
    repository: PromptOpsRepository = Depends(get_repository),
) -> ABTestSchema:
    service = build_ab_testing_service(repository, ctx)
    try:
        ab_test = await service.conclude(ab_test_id)
    except (ABTestNotFoundError, PromptVersionNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ABTestNotConclusiveError, EvaluationGateFailedError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _ab_test_schema(ab_test)


@router.get("/prompts/{prompt_name}/active", response_model=PromptVersionSchema)
async def get_active_prompt_version(
    prompt_name: str,
    tenant_id: str = Depends(resolve_tenant_id),
    repository: PromptOpsRepository = Depends(get_repository),
) -> PromptVersionSchema:
    version = await repository.get_active_prompt_version(tenant_id=tenant_id, prompt_name=prompt_name)
    if version is None:
        raise HTTPException(status_code=404, detail=str(NoActivePromptVersionError(prompt_name)))
    return _version_schema(version)
