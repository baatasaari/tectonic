"""`/v1/multi-tenancy/*` routes (LLD §3)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from multi_tenancy.api.deps import (
    build_environment_service,
    build_isolation_probe_service,
    build_organisation_service,
    build_tenant_registry_service,
    build_workspace_service,
    get_ctx,
    get_repository,
)
from multi_tenancy.app_context import AppContext
from multi_tenancy.core.domain import (
    EnvironmentNotFoundError,
    HierarchyStatus,
    InvalidTransitionError,
    OrganisationNotFoundError,
    ProbeTargetNotFoundError,
    TenantNotFoundError,
    TenantStatus,
    WorkspaceNotFoundError,
)
from multi_tenancy.core.ports import MultiTenancyRepository
from multi_tenancy.schemas.multi_tenancy import (
    EntitlementListResponse,
    EnvironmentListResponse,
    EnvironmentSchema,
    IsolationProbeResultListResponse,
    IsolationProbeResultSchema,
    OrganisationListResponse,
    OrganisationSchema,
    RegisterEnvironmentRequest,
    RegisterOrganisationRequest,
    RegisterTenantRequest,
    RegisterWorkspaceRequest,
    RunIsolationProbeRequest,
    SetEntitlementsRequest,
    SuspendRequest,
    SuspendTenantRequest,
    TenantGateResultSchema,
    TenantListResponse,
    TenantSchema,
    WorkspaceListResponse,
    WorkspaceSchema,
)

router = APIRouter(prefix="/v1/multi-tenancy", tags=["multi-tenancy"])


def _tenant_schema(tenant) -> TenantSchema:
    return TenantSchema(
        id=tenant.id, name=tenant.name, status=tenant.status.value, tier=tenant.tier,
        organisation_id=tenant.organisation_id, created_at=tenant.created_at, updated_at=tenant.updated_at,
    )


def _organisation_schema(org) -> OrganisationSchema:
    return OrganisationSchema(
        id=org.id, name=org.name, status=org.status.value, owner_identity_id=org.owner_identity_id,
        labels=org.labels, version=org.version, created_at=org.created_at, updated_at=org.updated_at,
    )


def _workspace_schema(ws) -> WorkspaceSchema:
    return WorkspaceSchema(
        id=ws.id, tenant_id=ws.tenant_id, name=ws.name, status=ws.status.value,
        owner_identity_id=ws.owner_identity_id, labels=ws.labels, version=ws.version,
        created_at=ws.created_at, updated_at=ws.updated_at,
    )


def _environment_schema(env) -> EnvironmentSchema:
    return EnvironmentSchema(
        id=env.id, workspace_id=env.workspace_id, name=env.name, kind=env.kind, region=env.region,
        status=env.status.value, owner_identity_id=env.owner_identity_id, labels=env.labels, version=env.version,
        created_at=env.created_at, updated_at=env.updated_at,
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
    ctx: AppContext = Depends(get_ctx),
    repository: MultiTenancyRepository = Depends(get_repository),
) -> TenantSchema:
    service = build_tenant_registry_service(repository, ctx)
    tenant = await service.register(name=body.name, tier=body.tier, organisation_id=body.organisation_id)
    return _tenant_schema(tenant)


@router.get("/tenants", response_model=TenantListResponse)
async def list_tenants(
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ctx: AppContext = Depends(get_ctx),
    repository: MultiTenancyRepository = Depends(get_repository),
) -> TenantListResponse:
    service = build_tenant_registry_service(repository, ctx)
    status_filter = TenantStatus(status) if status is not None else None
    tenants, total = await service.list(status=status_filter, limit=limit, offset=offset)
    return TenantListResponse(items=[_tenant_schema(t) for t in tenants], total=total, limit=limit, offset=offset)


@router.get("/tenants/{tenant_id}", response_model=TenantSchema)
async def get_tenant(
    tenant_id: str,
    ctx: AppContext = Depends(get_ctx),
    repository: MultiTenancyRepository = Depends(get_repository),
) -> TenantSchema:
    service = build_tenant_registry_service(repository, ctx)
    try:
        tenant = await service.get(tenant_id)
    except TenantNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _tenant_schema(tenant)


@router.get("/tenants/{tenant_id}/gate", response_model=TenantGateResultSchema)
async def tenant_gate(
    tenant_id: str,
    module: str | None = Query(None, description="If given, also checks this module against the tenant's entitlements"),
    ctx: AppContext = Depends(get_ctx),
    repository: MultiTenancyRepository = Depends(get_repository),
) -> TenantGateResultSchema:
    service = build_tenant_registry_service(repository, ctx)
    result = await service.gate(tenant_id, module=module)
    return TenantGateResultSchema(allowed=result.allowed, reason=result.reason)


@router.get("/tenants/{tenant_id}/entitlements", response_model=EntitlementListResponse)
async def list_entitlements(
    tenant_id: str,
    ctx: AppContext = Depends(get_ctx),
    repository: MultiTenancyRepository = Depends(get_repository),
) -> EntitlementListResponse:
    service = build_tenant_registry_service(repository, ctx)
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
    ctx: AppContext = Depends(get_ctx),
    repository: MultiTenancyRepository = Depends(get_repository),
) -> EntitlementListResponse:
    service = build_tenant_registry_service(repository, ctx)
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
    ctx: AppContext = Depends(get_ctx),
    repository: MultiTenancyRepository = Depends(get_repository),
) -> TenantSchema:
    service = build_tenant_registry_service(repository, ctx)
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
    ctx: AppContext = Depends(get_ctx),
    repository: MultiTenancyRepository = Depends(get_repository),
) -> TenantSchema:
    service = build_tenant_registry_service(repository, ctx)
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
    ctx: AppContext = Depends(get_ctx),
    repository: MultiTenancyRepository = Depends(get_repository),
) -> TenantSchema:
    service = build_tenant_registry_service(repository, ctx)
    try:
        tenant = await service.delete(tenant_id)
    except TenantNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _tenant_schema(tenant)


# --- Organisation ---


@router.post("/organisations", response_model=OrganisationSchema, status_code=201)
async def register_organisation(
    body: RegisterOrganisationRequest,
    ctx: AppContext = Depends(get_ctx),
    repository: MultiTenancyRepository = Depends(get_repository),
) -> OrganisationSchema:
    service = build_organisation_service(repository, ctx)
    org = await service.register(name=body.name, owner_identity_id=body.owner_identity_id)
    return _organisation_schema(org)


@router.get("/organisations", response_model=OrganisationListResponse)
async def list_organisations(
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ctx: AppContext = Depends(get_ctx),
    repository: MultiTenancyRepository = Depends(get_repository),
) -> OrganisationListResponse:
    service = build_organisation_service(repository, ctx)
    status_filter = HierarchyStatus(status) if status is not None else None
    orgs, total = await service.list(status=status_filter, limit=limit, offset=offset)
    return OrganisationListResponse(
        items=[_organisation_schema(o) for o in orgs], total=total, limit=limit, offset=offset,
    )


@router.get("/organisations/{organisation_id}", response_model=OrganisationSchema)
async def get_organisation(
    organisation_id: str,
    ctx: AppContext = Depends(get_ctx),
    repository: MultiTenancyRepository = Depends(get_repository),
) -> OrganisationSchema:
    service = build_organisation_service(repository, ctx)
    try:
        org = await service.get(organisation_id)
    except OrganisationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _organisation_schema(org)


@router.post("/organisations/{organisation_id}/suspend", response_model=OrganisationSchema)
async def suspend_organisation(
    organisation_id: str,
    body: SuspendRequest,
    ctx: AppContext = Depends(get_ctx),
    repository: MultiTenancyRepository = Depends(get_repository),
) -> OrganisationSchema:
    service = build_organisation_service(repository, ctx)
    try:
        org = await service.suspend(organisation_id, reason=body.reason)
    except OrganisationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _organisation_schema(org)


@router.post("/organisations/{organisation_id}/reactivate", response_model=OrganisationSchema)
async def reactivate_organisation(
    organisation_id: str,
    ctx: AppContext = Depends(get_ctx),
    repository: MultiTenancyRepository = Depends(get_repository),
) -> OrganisationSchema:
    service = build_organisation_service(repository, ctx)
    try:
        org = await service.reactivate(organisation_id)
    except OrganisationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _organisation_schema(org)


@router.post("/organisations/{organisation_id}/delete", response_model=OrganisationSchema)
async def delete_organisation(
    organisation_id: str,
    ctx: AppContext = Depends(get_ctx),
    repository: MultiTenancyRepository = Depends(get_repository),
) -> OrganisationSchema:
    service = build_organisation_service(repository, ctx)
    try:
        org = await service.delete(organisation_id)
    except OrganisationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _organisation_schema(org)


# --- Workspace ---


@router.post("/workspaces", response_model=WorkspaceSchema, status_code=201)
async def register_workspace(
    body: RegisterWorkspaceRequest,
    ctx: AppContext = Depends(get_ctx),
    repository: MultiTenancyRepository = Depends(get_repository),
) -> WorkspaceSchema:
    service = build_workspace_service(repository, ctx)
    try:
        ws = await service.register(tenant_id=body.tenant_id, name=body.name, owner_identity_id=body.owner_identity_id)
    except TenantNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _workspace_schema(ws)


@router.get("/workspaces", response_model=WorkspaceListResponse)
async def list_workspaces(
    tenant_id: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ctx: AppContext = Depends(get_ctx),
    repository: MultiTenancyRepository = Depends(get_repository),
) -> WorkspaceListResponse:
    service = build_workspace_service(repository, ctx)
    status_filter = HierarchyStatus(status) if status is not None else None
    workspaces, total = await service.list(tenant_id=tenant_id, status=status_filter, limit=limit, offset=offset)
    return WorkspaceListResponse(
        items=[_workspace_schema(w) for w in workspaces], total=total, limit=limit, offset=offset,
    )


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceSchema)
async def get_workspace(
    workspace_id: str,
    ctx: AppContext = Depends(get_ctx),
    repository: MultiTenancyRepository = Depends(get_repository),
) -> WorkspaceSchema:
    service = build_workspace_service(repository, ctx)
    try:
        ws = await service.get(workspace_id)
    except WorkspaceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _workspace_schema(ws)


@router.post("/workspaces/{workspace_id}/suspend", response_model=WorkspaceSchema)
async def suspend_workspace(
    workspace_id: str,
    body: SuspendRequest,
    ctx: AppContext = Depends(get_ctx),
    repository: MultiTenancyRepository = Depends(get_repository),
) -> WorkspaceSchema:
    service = build_workspace_service(repository, ctx)
    try:
        ws = await service.suspend(workspace_id, reason=body.reason)
    except WorkspaceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _workspace_schema(ws)


@router.post("/workspaces/{workspace_id}/reactivate", response_model=WorkspaceSchema)
async def reactivate_workspace(
    workspace_id: str,
    ctx: AppContext = Depends(get_ctx),
    repository: MultiTenancyRepository = Depends(get_repository),
) -> WorkspaceSchema:
    service = build_workspace_service(repository, ctx)
    try:
        ws = await service.reactivate(workspace_id)
    except WorkspaceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _workspace_schema(ws)


@router.post("/workspaces/{workspace_id}/delete", response_model=WorkspaceSchema)
async def delete_workspace(
    workspace_id: str,
    ctx: AppContext = Depends(get_ctx),
    repository: MultiTenancyRepository = Depends(get_repository),
) -> WorkspaceSchema:
    service = build_workspace_service(repository, ctx)
    try:
        ws = await service.delete(workspace_id)
    except WorkspaceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _workspace_schema(ws)


# --- Environment ---


@router.post("/environments", response_model=EnvironmentSchema, status_code=201)
async def register_environment(
    body: RegisterEnvironmentRequest,
    ctx: AppContext = Depends(get_ctx),
    repository: MultiTenancyRepository = Depends(get_repository),
) -> EnvironmentSchema:
    service = build_environment_service(repository, ctx)
    try:
        env = await service.register(
            workspace_id=body.workspace_id, name=body.name, kind=body.kind, region=body.region,
            owner_identity_id=body.owner_identity_id,
        )
    except WorkspaceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _environment_schema(env)


@router.get("/environments", response_model=EnvironmentListResponse)
async def list_environments(
    workspace_id: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ctx: AppContext = Depends(get_ctx),
    repository: MultiTenancyRepository = Depends(get_repository),
) -> EnvironmentListResponse:
    service = build_environment_service(repository, ctx)
    status_filter = HierarchyStatus(status) if status is not None else None
    environments, total = await service.list(
        workspace_id=workspace_id, status=status_filter, limit=limit, offset=offset,
    )
    return EnvironmentListResponse(
        items=[_environment_schema(e) for e in environments], total=total, limit=limit, offset=offset,
    )


@router.get("/environments/{environment_id}", response_model=EnvironmentSchema)
async def get_environment(
    environment_id: str,
    ctx: AppContext = Depends(get_ctx),
    repository: MultiTenancyRepository = Depends(get_repository),
) -> EnvironmentSchema:
    service = build_environment_service(repository, ctx)
    try:
        env = await service.get(environment_id)
    except EnvironmentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _environment_schema(env)


@router.post("/environments/{environment_id}/suspend", response_model=EnvironmentSchema)
async def suspend_environment(
    environment_id: str,
    body: SuspendRequest,
    ctx: AppContext = Depends(get_ctx),
    repository: MultiTenancyRepository = Depends(get_repository),
) -> EnvironmentSchema:
    service = build_environment_service(repository, ctx)
    try:
        env = await service.suspend(environment_id, reason=body.reason)
    except EnvironmentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _environment_schema(env)


@router.post("/environments/{environment_id}/reactivate", response_model=EnvironmentSchema)
async def reactivate_environment(
    environment_id: str,
    ctx: AppContext = Depends(get_ctx),
    repository: MultiTenancyRepository = Depends(get_repository),
) -> EnvironmentSchema:
    service = build_environment_service(repository, ctx)
    try:
        env = await service.reactivate(environment_id)
    except EnvironmentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _environment_schema(env)


@router.post("/environments/{environment_id}/delete", response_model=EnvironmentSchema)
async def delete_environment(
    environment_id: str,
    ctx: AppContext = Depends(get_ctx),
    repository: MultiTenancyRepository = Depends(get_repository),
) -> EnvironmentSchema:
    service = build_environment_service(repository, ctx)
    try:
        env = await service.delete(environment_id)
    except EnvironmentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _environment_schema(env)


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
