from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, Request

from identity_and_access.app_context import AppContext
from identity_and_access.core.authorization_service import AuthorizationService
from identity_and_access.core.group_service import GroupService
from identity_and_access.core.identity_provider_service import IdentityProviderService
from identity_and_access.core.identity_registry_service import IdentityRegistryService
from identity_and_access.core.oidc_federation_service import OidcFederationService
from identity_and_access.core.ports import IdentityAccessRepository
from identity_and_access.core.role_service import RoleService
from identity_and_access.core.scim_token_service import ScimTokenService
from identity_and_access.core.token_service import TokenService
from identity_and_access.db.repository import SQLAlchemyIdentityAccessRepository


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


def resolve_tenant_id(request: Request, ctx: AppContext = Depends(get_ctx)) -> str:
    return request.headers.get("X-Tenant-Id", ctx.settings.tenant_id)


async def get_repository(ctx: AppContext = Depends(get_ctx)) -> AsyncIterator[IdentityAccessRepository]:
    async with ctx.session_factory() as session:
        yield SQLAlchemyIdentityAccessRepository(session)


def build_identity_registry_service(repository: IdentityAccessRepository) -> IdentityRegistryService:
    return IdentityRegistryService(repository)


def build_role_service(repository: IdentityAccessRepository) -> RoleService:
    return RoleService(repository)


def build_token_service(repository: IdentityAccessRepository, ctx: AppContext) -> TokenService:
    return TokenService(repository, ctx.signer, default_ttl_seconds=ctx.settings.token_default_ttl_seconds)


def build_authorization_service(repository: IdentityAccessRepository, ctx: AppContext) -> AuthorizationService:
    return AuthorizationService(repository, ctx.signer, ctx.auditability)


def build_identity_provider_service(repository: IdentityAccessRepository) -> IdentityProviderService:
    return IdentityProviderService(repository)


def build_group_service(repository: IdentityAccessRepository) -> GroupService:
    return GroupService(repository)


def build_scim_token_service(repository: IdentityAccessRepository) -> ScimTokenService:
    return ScimTokenService(repository)


def build_oidc_federation_service(repository: IdentityAccessRepository, ctx: AppContext) -> OidcFederationService:
    return OidcFederationService(repository, ctx.oidc_verifier)
