"""`/v1/sdk-portal/*` routes (LLD §3).

Route ordering matters: the fixed-path collection routes
(`/catalog/sync`, `/adoption-rate`) are declared before the
parameterized routes they could otherwise collide with.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from sdk_and_developer_portal.api.deps import (
    build_adoption_metrics_service,
    build_developer_account_service,
    build_module_catalog_service,
    build_sdk_generator_service,
    get_ctx,
    get_repository,
)
from sdk_and_developer_portal.app_context import AppContext
from sdk_and_developer_portal.core.domain import (
    DeveloperNotFoundError,
    DeveloperRevokedError,
    DeveloperStatus,
    InvalidTransitionError,
    ModuleCatalogEntryNotFoundError,
    SdkPackageNotFoundError,
    UnsupportedSdkLanguageError,
)
from sdk_and_developer_portal.core.ports import PortalRepository
from sdk_and_developer_portal.schemas.sdk_and_developer_portal import (
    AdoptionMetricsSchema,
    AdoptionRateSchema,
    DeveloperAccountListResponse,
    DeveloperAccountSchema,
    GenerateSdkRequest,
    IssuedTokenSchema,
    IssueSandboxTokenRequest,
    ModuleCatalogEntrySchema,
    ModuleCatalogListResponse,
    RegisterDeveloperRequest,
    SdkPackageListResponse,
    SdkPackageSchema,
)

router = APIRouter(prefix="/v1/sdk-portal", tags=["sdk-portal"])


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


def _developer_schema(developer) -> DeveloperAccountSchema:
    return DeveloperAccountSchema(
        id=developer.id, name=developer.name, email=developer.email, tenant_id=developer.tenant_id,
        identity_id=developer.identity_id, status=developer.status.value,
        created_at=developer.created_at, updated_at=developer.updated_at,
    )


def _catalog_schema(entry) -> ModuleCatalogEntrySchema:
    return ModuleCatalogEntrySchema(
        module_name=entry.module_name, base_url=entry.base_url, title=entry.title, version=entry.version,
        path_count=entry.path_count, spec_json=entry.spec_json, spec_hash=entry.spec_hash,
        last_synced_at=entry.last_synced_at,
    )


def _sdk_schema(package) -> SdkPackageSchema:
    return SdkPackageSchema(
        id=package.id, module_name=package.module_name, language=package.language, version=package.version,
        source_code=package.source_code, spec_hash=package.spec_hash, generated_at=package.generated_at,
    )


@router.post("/developers", response_model=DeveloperAccountSchema, status_code=201)
async def register_developer(
    body: RegisterDeveloperRequest,
    ctx: AppContext = Depends(get_ctx),
    repository: PortalRepository = Depends(get_repository),
) -> DeveloperAccountSchema:
    service = build_developer_account_service(repository, ctx)
    developer = await service.register(name=body.name, email=body.email, role_names=body.role_names)
    return _developer_schema(developer)


@router.get("/developers", response_model=DeveloperAccountListResponse)
async def list_developers(
    status: DeveloperStatus | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ctx: AppContext = Depends(get_ctx),
    repository: PortalRepository = Depends(get_repository),
) -> DeveloperAccountListResponse:
    service = build_developer_account_service(repository, ctx)
    developers, total = await service.list(status=status, limit=limit, offset=offset)
    return DeveloperAccountListResponse(
        items=[_developer_schema(d) for d in developers], total=total, limit=limit, offset=offset,
    )


@router.get("/developers/{developer_id}", response_model=DeveloperAccountSchema)
async def get_developer(
    developer_id: str,
    ctx: AppContext = Depends(get_ctx),
    repository: PortalRepository = Depends(get_repository),
) -> DeveloperAccountSchema:
    service = build_developer_account_service(repository, ctx)
    try:
        developer = await service.get(developer_id)
    except DeveloperNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _developer_schema(developer)


@router.post("/developers/{developer_id}/revoke", response_model=DeveloperAccountSchema)
async def revoke_developer(
    developer_id: str,
    ctx: AppContext = Depends(get_ctx),
    repository: PortalRepository = Depends(get_repository),
) -> DeveloperAccountSchema:
    service = build_developer_account_service(repository, ctx)
    try:
        developer = await service.revoke(developer_id)
    except DeveloperNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _developer_schema(developer)


@router.post("/developers/{developer_id}/token", response_model=IssuedTokenSchema)
async def issue_sandbox_token(
    developer_id: str,
    body: IssueSandboxTokenRequest,
    ctx: AppContext = Depends(get_ctx),
    repository: PortalRepository = Depends(get_repository),
) -> IssuedTokenSchema:
    service = build_developer_account_service(repository, ctx)
    try:
        issued = await service.issue_sandbox_token(developer_id, requested_scopes=body.requested_scopes)
    except DeveloperNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DeveloperRevokedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return IssuedTokenSchema(token=issued["token"], granted_scopes=issued["granted_scopes"])


@router.get("/developers/{developer_id}/adoption", response_model=AdoptionMetricsSchema)
async def get_developer_adoption(
    developer_id: str,
    ctx: AppContext = Depends(get_ctx),
    repository: PortalRepository = Depends(get_repository),
) -> AdoptionMetricsSchema:
    service = build_adoption_metrics_service(repository, ctx)
    try:
        metrics = await service.time_to_first_call(developer_id)
    except DeveloperNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return AdoptionMetricsSchema(
        first_call_at=metrics.first_call_at, time_to_first_call_seconds=metrics.time_to_first_call_seconds,
    )


@router.get("/adoption-rate", response_model=AdoptionRateSchema)
async def get_adoption_rate(
    ctx: AppContext = Depends(get_ctx),
    repository: PortalRepository = Depends(get_repository),
) -> AdoptionRateSchema:
    service = build_adoption_metrics_service(repository, ctx)
    report = await service.adoption_rate()
    return AdoptionRateSchema(adopted_count=report.adopted_count, total_developers=report.total_developers, rate=report.rate)


@router.post("/catalog/sync", response_model=list[ModuleCatalogEntrySchema])
async def sync_catalog(
    ctx: AppContext = Depends(get_ctx),
    repository: PortalRepository = Depends(get_repository),
) -> list[ModuleCatalogEntrySchema]:
    service = build_module_catalog_service(repository, ctx)
    entries = await service.sync_catalog(ctx.settings.catalog_targets)
    return [_catalog_schema(e) for e in entries]


@router.get("/catalog", response_model=ModuleCatalogListResponse)
async def list_catalog(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ctx: AppContext = Depends(get_ctx),
    repository: PortalRepository = Depends(get_repository),
) -> ModuleCatalogListResponse:
    service = build_module_catalog_service(repository, ctx)
    entries, total = await service.list(limit=limit, offset=offset)
    return ModuleCatalogListResponse(items=[_catalog_schema(e) for e in entries], total=total, limit=limit, offset=offset)


@router.get("/catalog/{module_name}", response_model=ModuleCatalogEntrySchema)
async def get_catalog_entry(
    module_name: str,
    ctx: AppContext = Depends(get_ctx),
    repository: PortalRepository = Depends(get_repository),
) -> ModuleCatalogEntrySchema:
    service = build_module_catalog_service(repository, ctx)
    try:
        entry = await service.get(module_name)
    except ModuleCatalogEntryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _catalog_schema(entry)


@router.post("/sdks/generate", response_model=SdkPackageSchema, status_code=201)
async def generate_sdk(
    body: GenerateSdkRequest,
    ctx: AppContext = Depends(get_ctx),
    repository: PortalRepository = Depends(get_repository),
) -> SdkPackageSchema:
    service = build_sdk_generator_service(repository, ctx)
    try:
        package = await service.generate_sdk(module_name=body.module_name, language=body.language)
    except ModuleCatalogEntryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except UnsupportedSdkLanguageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _sdk_schema(package)


@router.get("/sdks", response_model=SdkPackageListResponse)
async def list_sdks(
    module_name: str | None = Query(None),
    language: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ctx: AppContext = Depends(get_ctx),
    repository: PortalRepository = Depends(get_repository),
) -> SdkPackageListResponse:
    _reject_null_byte_query(module_name=module_name, language=language)
    service = build_sdk_generator_service(repository, ctx)
    packages, total = await service.list(module_name=module_name, language=language, limit=limit, offset=offset)
    return SdkPackageListResponse(items=[_sdk_schema(p) for p in packages], total=total, limit=limit, offset=offset)


@router.get("/sdks/{package_id}", response_model=SdkPackageSchema)
async def get_sdk(
    package_id: str,
    ctx: AppContext = Depends(get_ctx),
    repository: PortalRepository = Depends(get_repository),
) -> SdkPackageSchema:
    service = build_sdk_generator_service(repository, ctx)
    try:
        package = await service.get(package_id)
    except SdkPackageNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _sdk_schema(package)
