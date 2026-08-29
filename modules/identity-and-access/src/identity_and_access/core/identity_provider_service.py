"""Identity Provider Service: CRUD for per-tenant OIDC/SAML federation
config (`core/domain.py::IdentityProviderRecord`). Pure config
management -- the actual login flow lives in
`core/oidc_federation_service.py`."""
from __future__ import annotations

from identity_and_access.core.domain import (
    IdentityProviderNotFoundError,
    IdentityProviderRecord,
    IdentityProviderType,
    new_id,
    now,
)
from identity_and_access.core.ports import IdentityAccessRepository


class IdentityProviderService:
    def __init__(self, repository: IdentityAccessRepository) -> None:
        self._repository = repository

    async def register(
        self, *, tenant_id: str, name: str, provider_type: IdentityProviderType, issuer: str,
        client_id: str = "", jwks_uri: str = "", sso_url: str = "", x509_certificate: str = "",
        email_claim: str = "email", groups_claim: str = "groups", name_claim: str = "name",
    ) -> IdentityProviderRecord:
        record = IdentityProviderRecord(
            id=new_id(), tenant_id=tenant_id, name=name, provider_type=provider_type, issuer=issuer,
            client_id=client_id, jwks_uri=jwks_uri, sso_url=sso_url, x509_certificate=x509_certificate,
            email_claim=email_claim, groups_claim=groups_claim, name_claim=name_claim,
        )
        return await self._repository.create_identity_provider(record)

    async def get(self, provider_id: str) -> IdentityProviderRecord:
        record = await self._repository.get_identity_provider(provider_id)
        if record is None:
            raise IdentityProviderNotFoundError(provider_id)
        return record

    async def list(
        self, *, tenant_id: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[IdentityProviderRecord], int]:
        return await self._repository.list_identity_providers(tenant_id=tenant_id, limit=limit, offset=offset)

    async def set_enabled(self, provider_id: str, enabled: bool) -> IdentityProviderRecord:
        record = await self.get(provider_id)
        record.enabled = enabled
        record.updated_at = now()
        return await self._repository.update_identity_provider(record)
