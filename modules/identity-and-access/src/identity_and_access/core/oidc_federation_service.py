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

SAML: handled by the sibling `SamlFederationService`
(`core/saml_federation_service.py`), not here -- `login()` below raises
`FederationError` for a non-OIDC provider rather than silently
no-op'ing or, worse, accepting an unverified assertion through the
wrong verifier. Both services share the identical
JIT-provisioning/group-role-resolution logic once a verified
`(subject, email, name, group_external_ids)` tuple is in hand
(`core/federation_common.py`) -- only the protocol-specific
verification step (`OidcTokenVerifier` here, `SamlAssertionVerifier`
there) differs.
"""
from __future__ import annotations

from identity_and_access.core.domain import (
    FederationError,
    IdentityProviderNotFoundError,
    IdentityProviderType,
    IdentityRecord,
)
from identity_and_access.core.federation_common import (
    jit_provision_or_update_identity,
    resolve_group_roles,
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
                "use SamlFederationService.login for a SAML provider",
            )

        claims = await self._verifier.verify(id_token=id_token, provider=provider)

        subject = claims.get("sub")
        if not subject:
            raise FederationError("id_token is missing the required 'sub' claim")
        email = claims.get(provider.email_claim)
        name = claims.get(provider.name_claim) or email or subject
        federated_role_names = await resolve_group_roles(
            self._repository, tenant_id=tenant_id, provider_id=provider_id,
            group_external_ids=claims.get(provider.groups_claim) or [],
        )

        return await jit_provision_or_update_identity(
            self._repository, tenant_id=tenant_id, provider_id=provider_id, subject=subject,
            email=email, name=name, federated_role_names=federated_role_names,
        )
