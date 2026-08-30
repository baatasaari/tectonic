"""Token Service (LLD §2 sub-components, §Level 3 "Token issuance"):
mints a scoped token narrowed to `requested ∩ granted` -- an identity's
actual role scopes are a ceiling `issue` can only ever narrow against,
never exceed, no matter what a caller requests.
"""
from __future__ import annotations

from identity_and_access.core.domain import (
    IdentityNotActiveError,
    IdentityNotFoundError,
    IdentityStatus,
    IssuedToken,
)
from identity_and_access.core.ports import IdentityAccessRepository
from identity_and_access.security.token_signer import JWTTokenSigner


class TokenService:
    def __init__(
        self, repository: IdentityAccessRepository, signer: JWTTokenSigner, *, default_ttl_seconds: int = 3600,
    ) -> None:
        self._repository = repository
        self._signer = signer
        self._default_ttl_seconds = default_ttl_seconds

    async def issue(
        self, *, identity_id: str, requested_scopes: list[str] | None = None, ttl_seconds: int | None = None,
    ) -> IssuedToken:
        identity = await self._repository.get_identity(identity_id)
        if identity is None:
            raise IdentityNotFoundError(identity_id)
        if identity.status != IdentityStatus.ACTIVE:
            raise IdentityNotActiveError(identity_id)

        # Manually-assigned role_names and federation-managed federated_role_names
        # (recomputed fresh from IdP group membership on every federated login --
        # see core/oidc_federation_service.py) are unioned here: a federated login
        # must never silently take away a role an operator granted by hand, and a
        # manually-granted role must never be required just to keep IdP-driven
        # access working.
        granted_pool: set[str] = set()
        for role_name in {*identity.role_names, *identity.federated_role_names}:
            role = await self._repository.get_role(identity.tenant_id, role_name)
            if role is not None:
                granted_pool.update(role.scopes)

        if requested_scopes is None:
            granted = sorted(granted_pool)
        else:
            granted = sorted(granted_pool & set(requested_scopes))

        token = self._signer.mint(
            identity_id=identity.id, tenant_id=identity.tenant_id, scopes=granted,
            ttl_seconds=ttl_seconds or self._default_ttl_seconds,
        )
        return IssuedToken(token=token, granted_scopes=granted)
