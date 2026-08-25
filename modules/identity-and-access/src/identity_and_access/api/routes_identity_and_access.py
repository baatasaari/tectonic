"""`/v1/identity-access/*` routes (LLD §3)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from identity_and_access.api.deps import (
    build_authorization_service,
    build_identity_registry_service,
    build_role_service,
    build_token_service,
    get_ctx,
    get_repository,
    resolve_tenant_id,
)
from identity_and_access.app_context import AppContext
from identity_and_access.core.domain import (
    IdentityNotActiveError,
    IdentityNotFoundError,
    IdentityStatus,
    IdentityType,
    InvalidTransitionError,
    RoleNotFoundError,
)
from identity_and_access.core.ports import IdentityAccessRepository
from identity_and_access.schemas.identity_and_access import (
    AuthDecisionListResponse,
    AuthDecisionResultSchema,
    AuthDecisionSchema,
    AuthorizeRequest,
    CreateRoleRequest,
    IdentityListResponse,
    IdentitySchema,
    IssuedTokenSchema,
    IssueTokenRequest,
    RegisterIdentityRequest,
    RoleListResponse,
    RoleSchema,
)

router = APIRouter(prefix="/v1/identity-access", tags=["identity-access"])


def _role_schema(role) -> RoleSchema:
    return RoleSchema(name=role.name, scopes=role.scopes, description=role.description, created_at=role.created_at)


def _identity_schema(identity) -> IdentitySchema:
    return IdentitySchema(
        id=identity.id, tenant_id=identity.tenant_id, name=identity.name, type=identity.type.value,
        status=identity.status.value, role_names=identity.role_names, created_at=identity.created_at,
        updated_at=identity.updated_at,
    )


def _auth_decision_schema(decision) -> AuthDecisionSchema:
    return AuthDecisionSchema(
        id=decision.id, tenant_id=decision.tenant_id, identity_id=decision.identity_id,
        required_scope=decision.required_scope, allowed=decision.allowed, reason=decision.reason,
        checked_at=decision.checked_at,
    )


@router.post("/roles", response_model=RoleSchema, status_code=201)
async def create_role(
    body: CreateRoleRequest,
    repository: IdentityAccessRepository = Depends(get_repository),
) -> RoleSchema:
    service = build_role_service(repository)
    role = await service.create(name=body.name, scopes=body.scopes, description=body.description)
    return _role_schema(role)


@router.get("/roles", response_model=RoleListResponse)
async def list_roles(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    repository: IdentityAccessRepository = Depends(get_repository),
) -> RoleListResponse:
    service = build_role_service(repository)
    roles, total = await service.list(limit=limit, offset=offset)
    return RoleListResponse(items=[_role_schema(r) for r in roles], total=total, limit=limit, offset=offset)


@router.post("/identities", response_model=IdentitySchema, status_code=201)
async def register_identity(
    body: RegisterIdentityRequest,
    tenant_id: str = Depends(resolve_tenant_id),
    repository: IdentityAccessRepository = Depends(get_repository),
) -> IdentitySchema:
    service = build_identity_registry_service(repository)
    try:
        identity = await service.register(
            tenant_id=tenant_id, name=body.name, type=IdentityType(body.type), role_names=body.role_names,
        )
    except RoleNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _identity_schema(identity)


@router.get("/identities", response_model=IdentityListResponse)
async def list_identities(
    tenant_id: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    repository: IdentityAccessRepository = Depends(get_repository),
) -> IdentityListResponse:
    service = build_identity_registry_service(repository)
    status_filter = IdentityStatus(status) if status is not None else None
    identities, total = await service.list(tenant_id=tenant_id, status=status_filter, limit=limit, offset=offset)
    return IdentityListResponse(
        items=[_identity_schema(i) for i in identities], total=total, limit=limit, offset=offset,
    )


@router.get("/identities/{identity_id}", response_model=IdentitySchema)
async def get_identity(
    identity_id: str,
    repository: IdentityAccessRepository = Depends(get_repository),
) -> IdentitySchema:
    service = build_identity_registry_service(repository)
    try:
        identity = await service.get(identity_id)
    except IdentityNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _identity_schema(identity)


@router.post("/identities/{identity_id}/revoke", response_model=IdentitySchema)
async def revoke_identity(
    identity_id: str,
    repository: IdentityAccessRepository = Depends(get_repository),
) -> IdentitySchema:
    service = build_identity_registry_service(repository)
    try:
        identity = await service.revoke(identity_id)
    except IdentityNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _identity_schema(identity)


@router.post("/identities/{identity_id}/reinstate", response_model=IdentitySchema)
async def reinstate_identity(
    identity_id: str,
    repository: IdentityAccessRepository = Depends(get_repository),
) -> IdentitySchema:
    service = build_identity_registry_service(repository)
    try:
        identity = await service.reinstate(identity_id)
    except IdentityNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _identity_schema(identity)


@router.get("/identities/{identity_id}/auth-decisions", response_model=AuthDecisionListResponse)
async def list_auth_decisions(
    identity_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    repository: IdentityAccessRepository = Depends(get_repository),
) -> AuthDecisionListResponse:
    decisions, total = await repository.list_auth_decisions(identity_id=identity_id, limit=limit, offset=offset)
    return AuthDecisionListResponse(
        items=[_auth_decision_schema(d) for d in decisions], total=total, limit=limit, offset=offset,
    )


@router.post("/tokens", response_model=IssuedTokenSchema, status_code=201)
async def issue_token(
    body: IssueTokenRequest,
    ctx: AppContext = Depends(get_ctx),
    repository: IdentityAccessRepository = Depends(get_repository),
) -> IssuedTokenSchema:
    service = build_token_service(repository, ctx)
    try:
        issued = await service.issue(
            identity_id=body.identity_id, requested_scopes=body.requested_scopes, ttl_seconds=body.ttl_seconds,
        )
    except IdentityNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except IdentityNotActiveError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return IssuedTokenSchema(token=issued.token, granted_scopes=issued.granted_scopes)


@router.post("/authorize", response_model=AuthDecisionResultSchema)
async def authorize(
    body: AuthorizeRequest,
    ctx: AppContext = Depends(get_ctx),
    repository: IdentityAccessRepository = Depends(get_repository),
) -> AuthDecisionResultSchema:
    service = build_authorization_service(repository, ctx)
    result = await service.authorize(token=body.token, required_scope=body.required_scope)
    return AuthDecisionResultSchema(allowed=result.allowed, reason=result.reason)
