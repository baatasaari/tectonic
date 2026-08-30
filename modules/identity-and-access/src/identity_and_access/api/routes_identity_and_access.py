"""`/v1/identity-access/*` routes (LLD §3)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from identity_and_access.api.deps import (
    build_authorization_service,
    build_group_service,
    build_identity_provider_service,
    build_identity_registry_service,
    build_oidc_federation_service,
    build_role_binding_service,
    build_role_service,
    build_saml_federation_service,
    build_scim_token_service,
    build_token_service,
    get_ctx,
    get_repository,
    resolve_tenant_id,
)
from identity_and_access.app_context import AppContext
from identity_and_access.core.domain import (
    FederationError,
    GroupNotFoundError,
    IdentityNotActiveError,
    IdentityNotFoundError,
    IdentityProviderNotFoundError,
    IdentityProviderType,
    IdentityStatus,
    IdentityType,
    InvalidTransitionError,
    RoleAlreadyExistsError,
    RoleNotFoundError,
    RoleNotGrantedError,
)
from identity_and_access.core.ports import IdentityAccessRepository
from identity_and_access.schemas.identity_and_access import (
    AuthDecisionListResponse,
    AuthDecisionResultSchema,
    AuthDecisionSchema,
    AuthorizeRequest,
    CreateRoleRequest,
    CreateScimTokenRequest,
    GrantRoleRequest,
    GroupListResponse,
    GroupSchema,
    IdentityListResponse,
    IdentityProviderListResponse,
    IdentityProviderSchema,
    IdentitySchema,
    IssuedTokenSchema,
    IssueTokenRequest,
    OidcLoginRequest,
    RegisterGroupRequest,
    RegisterIdentityProviderRequest,
    RegisterIdentityRequest,
    RoleBindingListResponse,
    RoleBindingSchema,
    RoleListResponse,
    RoleSchema,
    SamlLoginRequest,
    ScimTokenCreatedSchema,
    ScimTokenListResponse,
    ScimTokenSchema,
    SetGroupRolesRequest,
)

router = APIRouter(prefix="/v1/identity-access", tags=["identity-access"])


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


def _role_schema(role) -> RoleSchema:
    return RoleSchema(
        id=role.id, tenant_id=role.tenant_id, name=role.name, scopes=role.scopes,
        description=role.description, created_at=role.created_at,
    )


def _role_binding_schema(binding) -> RoleBindingSchema:
    return RoleBindingSchema(
        id=binding.id, tenant_id=binding.tenant_id, identity_id=binding.identity_id, role_name=binding.role_name,
        granted_by=binding.granted_by, granted_at=binding.granted_at, revoked_at=binding.revoked_at,
    )


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
    tenant_id: str = Depends(resolve_tenant_id),
    repository: IdentityAccessRepository = Depends(get_repository),
) -> RoleSchema:
    service = build_role_service(repository)
    try:
        role = await service.create(
            tenant_id=tenant_id, name=body.name, scopes=body.scopes, description=body.description,
        )
    except RoleAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _role_schema(role)


@router.get("/roles", response_model=RoleListResponse)
async def list_roles(
    tenant_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    repository: IdentityAccessRepository = Depends(get_repository),
) -> RoleListResponse:
    _reject_null_byte_query(tenant_id=tenant_id)
    service = build_role_service(repository)
    roles, total = await service.list(tenant_id=tenant_id, limit=limit, offset=offset)
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
    status: IdentityStatus | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    repository: IdentityAccessRepository = Depends(get_repository),
) -> IdentityListResponse:
    _reject_null_byte_query(tenant_id=tenant_id)
    service = build_identity_registry_service(repository)
    identities, total = await service.list(tenant_id=tenant_id, status=status, limit=limit, offset=offset)
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


@router.post("/identities/{identity_id}/roles", response_model=IdentitySchema, status_code=201)
async def grant_role(
    identity_id: str,
    body: GrantRoleRequest,
    repository: IdentityAccessRepository = Depends(get_repository),
) -> IdentitySchema:
    service = build_role_binding_service(repository)
    try:
        identity = await service.grant(identity_id=identity_id, role_name=body.role_name, granted_by=body.granted_by)
    except IdentityNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RoleNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _identity_schema(identity)


@router.post("/identities/{identity_id}/roles/{role_name}/revoke", response_model=IdentitySchema)
async def revoke_role(
    identity_id: str,
    role_name: str,
    repository: IdentityAccessRepository = Depends(get_repository),
) -> IdentitySchema:
    service = build_role_binding_service(repository)
    try:
        identity = await service.revoke(identity_id=identity_id, role_name=role_name)
    except IdentityNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RoleNotGrantedError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _identity_schema(identity)


@router.get("/identities/{identity_id}/role-bindings", response_model=RoleBindingListResponse)
async def list_identity_role_bindings(
    identity_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    repository: IdentityAccessRepository = Depends(get_repository),
) -> RoleBindingListResponse:
    service = build_role_binding_service(repository)
    bindings, total = await service.list_bindings(identity_id=identity_id, limit=limit, offset=offset)
    return RoleBindingListResponse(
        items=[_role_binding_schema(b) for b in bindings], total=total, limit=limit, offset=offset,
    )


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


def _provider_schema(provider) -> IdentityProviderSchema:
    return IdentityProviderSchema(
        id=provider.id, tenant_id=provider.tenant_id, name=provider.name, provider_type=provider.provider_type.value,
        issuer=provider.issuer, enabled=provider.enabled, client_id=provider.client_id, jwks_uri=provider.jwks_uri,
        sso_url=provider.sso_url, email_claim=provider.email_claim, groups_claim=provider.groups_claim,
        name_claim=provider.name_claim, created_at=provider.created_at, updated_at=provider.updated_at,
    )


def _group_schema(group) -> GroupSchema:
    return GroupSchema(
        id=group.id, tenant_id=group.tenant_id, provider_id=group.provider_id, external_id=group.external_id,
        name=group.name, default_role_names=group.default_role_names, created_at=group.created_at,
    )


def _scim_token_schema(token) -> ScimTokenSchema:
    return ScimTokenSchema(id=token.id, tenant_id=token.tenant_id, name=token.name, revoked=token.revoked, created_at=token.created_at)


@router.post("/identity-providers", response_model=IdentityProviderSchema, status_code=201)
async def register_identity_provider(
    body: RegisterIdentityProviderRequest,
    tenant_id: str = Depends(resolve_tenant_id),
    repository: IdentityAccessRepository = Depends(get_repository),
) -> IdentityProviderSchema:
    service = build_identity_provider_service(repository)
    provider = await service.register(
        tenant_id=tenant_id, name=body.name, provider_type=IdentityProviderType(body.provider_type),
        issuer=body.issuer, client_id=body.client_id, jwks_uri=body.jwks_uri, sso_url=body.sso_url,
        x509_certificate=body.x509_certificate, email_claim=body.email_claim, groups_claim=body.groups_claim,
        name_claim=body.name_claim,
    )
    return _provider_schema(provider)


@router.get("/identity-providers", response_model=IdentityProviderListResponse)
async def list_identity_providers(
    tenant_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    repository: IdentityAccessRepository = Depends(get_repository),
) -> IdentityProviderListResponse:
    _reject_null_byte_query(tenant_id=tenant_id)
    service = build_identity_provider_service(repository)
    providers, total = await service.list(tenant_id=tenant_id, limit=limit, offset=offset)
    return IdentityProviderListResponse(
        items=[_provider_schema(p) for p in providers], total=total, limit=limit, offset=offset,
    )


@router.get("/identity-providers/{provider_id}", response_model=IdentityProviderSchema)
async def get_identity_provider(
    provider_id: str,
    repository: IdentityAccessRepository = Depends(get_repository),
) -> IdentityProviderSchema:
    service = build_identity_provider_service(repository)
    try:
        provider = await service.get(provider_id)
    except IdentityProviderNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _provider_schema(provider)


@router.post("/identity-providers/{provider_id}/disable", response_model=IdentityProviderSchema)
async def disable_identity_provider(
    provider_id: str,
    repository: IdentityAccessRepository = Depends(get_repository),
) -> IdentityProviderSchema:
    service = build_identity_provider_service(repository)
    try:
        provider = await service.set_enabled(provider_id, False)
    except IdentityProviderNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _provider_schema(provider)


@router.post("/identity-providers/{provider_id}/enable", response_model=IdentityProviderSchema)
async def enable_identity_provider(
    provider_id: str,
    repository: IdentityAccessRepository = Depends(get_repository),
) -> IdentityProviderSchema:
    service = build_identity_provider_service(repository)
    try:
        provider = await service.set_enabled(provider_id, True)
    except IdentityProviderNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _provider_schema(provider)


@router.post("/oidc/login", response_model=IdentitySchema)
async def oidc_login(
    body: OidcLoginRequest,
    tenant_id: str = Depends(resolve_tenant_id),
    ctx: AppContext = Depends(get_ctx),
    repository: IdentityAccessRepository = Depends(get_repository),
) -> IdentitySchema:
    service = build_oidc_federation_service(repository, ctx)
    try:
        identity = await service.login(tenant_id=tenant_id, provider_id=body.provider_id, id_token=body.id_token)
    except IdentityProviderNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FederationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return _identity_schema(identity)


@router.post("/saml/login", response_model=IdentitySchema)
async def saml_login(
    body: SamlLoginRequest,
    tenant_id: str = Depends(resolve_tenant_id),
    ctx: AppContext = Depends(get_ctx),
    repository: IdentityAccessRepository = Depends(get_repository),
) -> IdentitySchema:
    """SAML 2.0 assertion consumer (ACS): verifies `saml_response`'s real
    XML-DSig signature and JIT-provisions/updates the matching identity
    the same way `/oidc/login` does for OIDC -- see
    `security/saml_verifier.py` and `core/saml_federation_service.py`."""
    service = build_saml_federation_service(repository, ctx)
    try:
        identity = await service.login(tenant_id=tenant_id, provider_id=body.provider_id, saml_response=body.saml_response)
    except IdentityProviderNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FederationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return _identity_schema(identity)


@router.post("/groups", response_model=GroupSchema, status_code=201)
async def register_group(
    body: RegisterGroupRequest,
    tenant_id: str = Depends(resolve_tenant_id),
    repository: IdentityAccessRepository = Depends(get_repository),
) -> GroupSchema:
    service = build_group_service(repository)
    group = await service.register(
        tenant_id=tenant_id, provider_id=body.provider_id, external_id=body.external_id, name=body.name,
        default_role_names=body.default_role_names,
    )
    return _group_schema(group)


@router.get("/groups", response_model=GroupListResponse)
async def list_groups(
    tenant_id: str | None = Query(None),
    provider_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    repository: IdentityAccessRepository = Depends(get_repository),
) -> GroupListResponse:
    _reject_null_byte_query(tenant_id=tenant_id, provider_id=provider_id)
    service = build_group_service(repository)
    groups, total = await service.list(tenant_id=tenant_id, provider_id=provider_id, limit=limit, offset=offset)
    return GroupListResponse(items=[_group_schema(g) for g in groups], total=total, limit=limit, offset=offset)


@router.get("/groups/{group_id}", response_model=GroupSchema)
async def get_group(
    group_id: str,
    repository: IdentityAccessRepository = Depends(get_repository),
) -> GroupSchema:
    service = build_group_service(repository)
    try:
        group = await service.get(group_id)
    except GroupNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _group_schema(group)


@router.post("/groups/{group_id}/roles", response_model=GroupSchema)
async def set_group_roles(
    group_id: str,
    body: SetGroupRolesRequest,
    repository: IdentityAccessRepository = Depends(get_repository),
) -> GroupSchema:
    service = build_group_service(repository)
    try:
        group = await service.set_default_role_names(group_id, body.role_names)
    except GroupNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _group_schema(group)


@router.post("/scim-tokens", response_model=ScimTokenCreatedSchema, status_code=201)
async def create_scim_token(
    body: CreateScimTokenRequest,
    tenant_id: str = Depends(resolve_tenant_id),
    repository: IdentityAccessRepository = Depends(get_repository),
) -> ScimTokenCreatedSchema:
    service = build_scim_token_service(repository)
    stored, cleartext = await service.create(tenant_id=tenant_id, name=body.name)
    return ScimTokenCreatedSchema(
        id=stored.id, tenant_id=stored.tenant_id, name=stored.name, token=cleartext, created_at=stored.created_at,
    )


@router.get("/scim-tokens", response_model=ScimTokenListResponse)
async def list_scim_tokens(
    tenant_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    repository: IdentityAccessRepository = Depends(get_repository),
) -> ScimTokenListResponse:
    _reject_null_byte_query(tenant_id=tenant_id)
    service = build_scim_token_service(repository)
    tokens, total = await service.list(tenant_id=tenant_id, limit=limit, offset=offset)
    return ScimTokenListResponse(items=[_scim_token_schema(t) for t in tokens], total=total, limit=limit, offset=offset)


@router.post("/scim-tokens/{token_id}/revoke", response_model=ScimTokenSchema)
async def revoke_scim_token(
    token_id: str,
    repository: IdentityAccessRepository = Depends(get_repository),
) -> ScimTokenSchema:
    service = build_scim_token_service(repository)
    token = await service.revoke(token_id)
    if token is None:
        raise HTTPException(status_code=404, detail=f"SCIM token not found: {token_id}")
    return _scim_token_schema(token)
