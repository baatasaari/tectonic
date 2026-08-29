"""SCIM's own authentication: a per-tenant bearer token
(`core/scim_token_service.py`), verified independently of
`security/jwt_auth.py`'s `ServiceAuthMiddleware` -- see that module's
docstring for why SCIM needs a separate scheme (an external IdP never
holds `TECTONIC_JWT_SHARED_SECRET`) and `jwt_auth.py`'s
`_EXCLUDED_PATH_PREFIXES` for how `/scim/*` is carved out of the
middleware that would otherwise reject every SCIM request outright.

A FastAPI dependency, not middleware: unlike the platform-wide service
JWT, this check needs the request's `{tenant_id}` path parameter (SCIM's
own routes are per-tenant, `/scim/v2/{tenant_id}/Users`) which only
FastAPI's own routing resolves -- middleware runs before that and only
sees the raw path.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from identity_and_access.api.deps import get_ctx, get_repository
from identity_and_access.app_context import AppContext
from identity_and_access.core.domain import ScimTokenInvalidError
from identity_and_access.core.ports import IdentityAccessRepository
from identity_and_access.core.scim_token_service import ScimTokenService


async def require_scim_token(
    tenant_id: str,
    request: Request,
    repository: IdentityAccessRepository = Depends(get_repository),
    ctx: AppContext = Depends(get_ctx),
) -> str:
    """Returns `tenant_id` on success (so route handlers can `Depends()`
    on this directly in place of a bare path parameter and get
    authentication for free); raises 401 otherwise."""
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="missing bearer token")

    service = ScimTokenService(repository)
    try:
        await service.authenticate(tenant_id=tenant_id, cleartext_token=token)
    except ScimTokenInvalidError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return tenant_id
