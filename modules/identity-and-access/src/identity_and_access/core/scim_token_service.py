"""SCIM Token Service: mints and verifies the per-tenant bearer token an
external IdP uses to authenticate its SCIM provisioning calls
(`security/scim_auth.py`, `api/routes_scim.py`) -- independent of this
module's own `TECTONIC_JWT_SHARED_SECRET`, which an external IdP never
holds. Same show-once posture this platform typically takes for API
keys: the cleartext token is returned exactly once, from `create()`;
only its SHA-256 hash is ever stored, so a leaked database backup does
not hand out working tokens."""
from __future__ import annotations

import hashlib
import secrets

from identity_and_access.core.domain import ScimTokenInvalidError, ScimTokenRecord, new_id
from identity_and_access.core.ports import IdentityAccessRepository


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class ScimTokenService:
    def __init__(self, repository: IdentityAccessRepository) -> None:
        self._repository = repository

    async def create(self, *, tenant_id: str, name: str) -> tuple[ScimTokenRecord, str]:
        """Returns (stored record, cleartext token) -- the caller must
        show the cleartext token to the operator now; it cannot be
        recovered afterward."""
        cleartext = secrets.token_urlsafe(32)
        record = ScimTokenRecord(id=new_id(), tenant_id=tenant_id, name=name, token_hash=_hash(cleartext))
        stored = await self._repository.create_scim_token(record)
        return stored, cleartext

    async def list(
        self, *, tenant_id: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[ScimTokenRecord], int]:
        return await self._repository.list_scim_tokens(tenant_id=tenant_id, limit=limit, offset=offset)

    async def revoke(self, token_id: str) -> ScimTokenRecord | None:
        return await self._repository.revoke_scim_token(token_id)

    async def authenticate(self, *, tenant_id: str, cleartext_token: str) -> ScimTokenRecord:
        """Raises ScimTokenInvalidError if the token is unknown, revoked,
        or doesn't belong to `tenant_id` -- one exception for every
        failure mode so `security/scim_auth.py` never leaks which case it
        was to the caller (a token for tenant A must look identical to no
        token at all when presented against tenant B's SCIM endpoint)."""
        record = await self._repository.get_scim_token_by_hash(_hash(cleartext_token))
        if record is None or record.revoked or record.tenant_id != tenant_id:
            raise ScimTokenInvalidError()
        return record
