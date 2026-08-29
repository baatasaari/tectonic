"""SAML Federation Service -- the SAML sibling of
`core/oidc_federation_service.py`. Verifies a SAML 2.0 assertion against
a tenant's registered IdP and JIT-provisions or updates the matching
identity, sharing that provisioning logic with the OIDC path via
`core/federation_common.py`.

JIT provisioning: identical semantics to OIDC -- looked up by
`(tenant_id, provider_id, external_subject)` (the assertion's `NameID`,
this provider's own durable per-user identifier), never by email;
`federated_role_names` is recomputed from scratch on every login from
the assertion's *current* group-bearing attribute (`provider.groups_claim`,
reused here as the SAML `Attribute/@Name` that carries group
membership -- IdPs disagree on this name the same way they disagree on
OIDC claim names, so it's the same per-provider config field, not a
SAML-only duplicate).
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
from identity_and_access.core.ports import IdentityAccessRepository, SamlAssertionVerifier


class SamlFederationService:
    def __init__(self, repository: IdentityAccessRepository, verifier: SamlAssertionVerifier) -> None:
        self._repository = repository
        self._verifier = verifier

    async def login(self, *, tenant_id: str, provider_id: str, saml_response: str) -> IdentityRecord:
        provider = await self._repository.get_identity_provider(provider_id)
        if provider is None or provider.tenant_id != tenant_id:
            raise IdentityProviderNotFoundError(provider_id)
        if not provider.enabled:
            raise FederationError(f"identity provider is disabled: {provider_id}")
        if provider.provider_type != IdentityProviderType.SAML:
            raise FederationError(
                f"provider {provider_id} is {provider.provider_type.value}, not saml -- "
                "use OidcFederationService.login for an OIDC provider",
            )

        claims = await self._verifier.verify(saml_response=saml_response, provider=provider)

        subject = claims.get("sub")
        if not subject:
            raise FederationError("SAML assertion is missing a Subject/NameID")
        email = claims.get(provider.email_claim)
        name = claims.get(provider.name_claim) or email or subject
        group_values = claims.get(provider.groups_claim) or []
        group_external_ids = group_values if isinstance(group_values, list) else [group_values]
        federated_role_names = await resolve_group_roles(
            self._repository, tenant_id=tenant_id, provider_id=provider_id, group_external_ids=group_external_ids,
        )

        return await jit_provision_or_update_identity(
            self._repository, tenant_id=tenant_id, provider_id=provider_id, subject=subject,
            email=email, name=name, federated_role_names=federated_role_names,
        )
