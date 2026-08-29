"""OIDC Federation Service (independent architecture assessment §31:
"no complete OIDC/SAML federation ... user/group/membership lifecycle
... tenant role bindings"): verifies an OIDC ID token against a
tenant's registered provider and JIT-provisions or updates the matching
identity.

JIT provisioning: an identity is looked up by (tenant_id, provider_id,
external_subject) -- the `sub` claim, this provider's own durable
per-user identifier -- never by email (an IdP-side email change must
never fork a second identity, and email addresses are reused/reassigned
in the wild in a way `sub` never is). First login for a given subject
creates a new IdentityRecord; every subsequent login updates its
`email`/`name`-derived `name` and, critically, recomputes
`federated_role_names` from scratch from the token's current groups
claim -- so removing someone from an IdP group revokes the roles that
group granted on their very next login, without needing this module to
poll the IdP or wait for a SCIM deprovisioning call.

SAML: deliberately not implemented here. `IdentityProviderRecord`
carries `provider_type=SAML`/`sso_url`/`x509_certificate` as a real,
storable config shape, but this module has no SAML assertion consumer
service (ACS) endpoint and performs no XML-DSig verification anywhere.
A real one is a substantial, security-critical undertaking (canonical
XML, signature-wrapping-attack defenses, `xmlsec`-grade tooling) that's
out of scope for this pass; `login()` raises FederationError for a
non-OIDC provider rather than silently no-op'ing or, worse, accepting an
unverified assertion.
"""
from __future__ import annotations

from identity_and_access.core.domain import (
    FederationError,
    IdentityProviderNotFoundError,
    IdentityProviderType,
    IdentityRecord,
    IdentityType,
    new_id,
    now,
)
from identity_and_access.core.ports import IdentityAccessRepository, OidcTokenVerifier


class OidcFederationService:
    def __init__(self, repository: IdentityAccessRepository, verifier: OidcTokenVerifier) -> None:
        self._repository = repository
        self._verifier = verifier

    async def login(self, *, tenant_id: str, provider_id: str, id_token: str) -> IdentityRecord:
        provider = await self._repository.get_identity_provider(provider_id)
        if provider is None or provider.tenant_id != tenant_id:
            raise IdentityProviderNotFoundError(provider_id)
        if not provider.enabled:
            raise FederationError(f"identity provider is disabled: {provider_id}")
        if provider.provider_type != IdentityProviderType.OIDC:
            raise FederationError(
                f"provider {provider_id} is {provider.provider_type.value}, not oidc -- "
                "SAML assertion verification is not implemented, see this module's README",
            )

        claims = await self._verifier.verify(id_token=id_token, provider=provider)

        subject = claims.get("sub")
        if not subject:
            raise FederationError("id_token is missing the required 'sub' claim")
        email = claims.get(provider.email_claim)
        name = claims.get(provider.name_claim) or email or subject
        federated_role_names = await self._resolve_group_roles(
            tenant_id=tenant_id, provider_id=provider_id, group_external_ids=claims.get(provider.groups_claim) or [],
        )

        existing = await self._repository.find_identity_by_external_subject(
            tenant_id=tenant_id, provider_id=provider_id, external_subject=subject,
        )
        if existing is None:
            record = IdentityRecord(
                id=new_id(), tenant_id=tenant_id, name=name, type=IdentityType.USER, email=email,
                external_provider_id=provider_id, external_subject=subject,
                federated_role_names=federated_role_names,
            )
            return await self._repository.create_identity(record)

        existing.name = name
        existing.email = email
        existing.federated_role_names = federated_role_names
        existing.updated_at = now()
        return await self._repository.update_identity(existing)

    async def _resolve_group_roles(
        self, *, tenant_id: str, provider_id: str, group_external_ids: list[str],
    ) -> list[str]:
        role_names: set[str] = set()
        for external_id in group_external_ids:
            group = await self._repository.find_group_by_external_id(
                tenant_id=tenant_id, provider_id=provider_id, external_id=external_id,
            )
            if group is not None:
                role_names.update(group.default_role_names)
        return sorted(role_names)
