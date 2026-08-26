"""`/v1/multi-tenancy/*` routes (LLD §3)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from multi_tenancy.api.deps import (
    build_isolation_probe_service,
    build_tenant_registry_service,
    get_ctx,
    get_repository,
)
from multi_tenancy.app_context import AppContext
from multi_tenancy.core.domain import (
    InvalidTransitionError,
    ProbeTargetNotFoundError,
    TenantNotFoundError,
    TenantStatus,
)
from multi_tenancy.core.ports import MultiTenancyRepository
from multi_tenancy.schemas.multi_tenancy import (
    EntitlementListResponse,
    IsolationProbeResultListResponse,
    IsolationProbeResultSchema,
    RegisterTenantRequest,
    RunIsolationProbeRequest,
    SetEntitlementsRequest,
    SuspendTenantRequest,
    TenantGateResultSchema,
    TenantListResponse,
    TenantSchema,
)

router = APIRouter(prefix="/v1/multi-tenancy", tags=["multi-tenancy"])


def _tenant_schema(tenant) -> TenantSchema:
    return TenantSchema(
        id=tenant.id, name=tenant.name, status=tenant.status.value, tier=tenant.tier,
        created_at=tenant.created_at, updated_at=tenant.updated_at,
    )


def _probe_result_schema(result) -> IsolationProbeResultSchema:
    return IsolationProbeResultSchema(
        id=result.id, tenant_id=result.tenant_id, target_name=result.target_name, passed=result.passed,
        breach_count=result.breach_count, sample_size=result.sample_size, details=result.details,
        checked_at=result.checked_at,
    )


@router.post("/tenants", response_model=TenantSchema, status_code=201)
async def register_tenant(
    body: RegisterTenantRequest,
    repository: MultiTenancyRepository = Depends(get_repository),
) -> TenantSchema:
    service = build_tenant_registry_service(repository)
    tenant = await service.register(name=body.name, tier=body.tier)
    return _tenant_schema(tenant)


@router.get("/tenants", response_model=TenantListResponse)
async def list_tenants(
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    repository: MultiTenancyRepository = Depends(get_repository),
) -> TenantListResponse:
    service = build_tenant_registry_service(repository)
    status_filter = TenantStatus(status) if status is not None else None
    tenants, total = await service.list(status=status_filter, limit=limit, offset=offset)
    return TenantListResponse(items=[_tenant_schema(t) for t in tenants], total=total, limit=limit, offset=offset)


@router.get("/tenants/{tenant_id}", response_model=TenantSchema)
async def get_tenant(
    tenant_id: str,
    repository: MultiTenancyRepository = Depends(get_repository),
) -> TenantSchema:
    service = build_tenant_registry_service(repository)
    try:
        tenant = await service.get(tenant_id)
    except TenantNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _tenant_schema(tenant)


@router.get("/tenants/{tenant_id}/gate", response_model=TenantGateResultSchema)
async def tenant_gate(
    tenant_id: str,
    module: str | None = Query(None, description="If given, also checks this module against the tenant's entitlements"),
    repository: MultiTenancyRepository = Depends(get_repository),
) -> TenantGateResultSchema:
    service = build_tenant_registry_service(repository)
    result = await service.gate(tenant_id, module=module)
    return TenantGateResultSchema(allowed=result.allowed, reason=result.reason)


@router.get("/tenants/{tenant_id}/entitlements", response_model=EntitlementListResponse)
async def list_entitlements(
    tenant_id: str,
    repository: MultiTenancyRepository = Depends(get_repository),
) -> EntitlementListResponse:
    service = build_tenant_registry_service(repository)
    try:
        tenant = await service.get(tenant_id)
        entitlements = await service.list_entitlements(tenant_id)
    except TenantNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return EntitlementListResponse(
        tenant_id=tenant_id, module_names=[e.module_name for e in entitlements],
        configured=tenant.entitlements_configured_at is not None,
    )


@router.post("/tenants/{tenant_id}/entitlements", response_model=EntitlementListResponse)
async def set_entitlements(
    tenant_id: str,
    body: SetEntitlementsRequest,
    repository: MultiTenancyRepository = Depends(get_repository),
) -> EntitlementListResponse:
    service = build_tenant_registry_service(repository)
    try:
        entitlements = await service.set_entitlements(tenant_id, module_names=body.module_names)
    except TenantNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return EntitlementListResponse(
        tenant_id=tenant_id, module_names=[e.module_name for e in entitlements], configured=True,
    )


@router.post("/tenants/{tenant_id}/suspend", response_model=TenantSchema)
async def suspend_tenant(
    tenant_id: str,
    body: SuspendTenantRequest,
    repository: MultiTenancyRepository = Depends(get_repository),
) -> TenantSchema:
    service = build_tenant_registry_service(repository)
    try:
        tenant = await service.suspend(tenant_id, reason=body.reason)
    except TenantNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _tenant_schema(tenant)


@router.post("/tenants/{tenant_id}/reactivate", response_model=TenantSchema)
async def reactivate_tenant(
    tenant_id: str,
    repository: MultiTenancyRepository = Depends(get_repository),
) -> TenantSchema:
    service = build_tenant_registry_service(repository)
    try:
        tenant = await service.reactivate(tenant_id)
    except TenantNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _tenant_schema(tenant)


@router.post("/tenants/{tenant_id}/delete", response_model=TenantSchema)
async def delete_tenant(
    tenant_id: str,
    repository: MultiTenancyRepository = Depends(get_repository),
) -> TenantSchema:
    service = build_tenant_registry_service(repository)
    try:
        tenant = await service.delete(tenant_id)
    except TenantNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _tenant_schema(tenant)


@router.post("/isolation-probes", response_model=IsolationProbeResultSchema, status_code=201)
async def run_isolation_probe(
    body: RunIsolationProbeRequest,
    ctx: AppContext = Depends(get_ctx),
    repository: MultiTenancyRepository = Depends(get_repository),
) -> IsolationProbeResultSchema:
    service = build_isolation_probe_service(repository, ctx)
    try:
        result = await service.run_probe(tenant_id=body.tenant_id, target_name=body.target_name)
    except ProbeTargetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _probe_result_schema(result)


@router.get("/isolation-probes", response_model=IsolationProbeResultListResponse)
async def list_isolation_probes(
    tenant_id: str | None = Query(None),
    target_name: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    repository: MultiTenancyRepository = Depends(get_repository),
) -> IsolationProbeResultListResponse:
    results, total = await repository.list_probe_results(
        tenant_id=tenant_id, target_name=target_name, limit=limit, offset=offset,
    )
    return IsolationProbeResultListResponse(
        items=[_probe_result_schema(r) for r in results], total=total, limit=limit, offset=offset,
    )
