"""Abstract ports this module depends on: persistence, the real
Auditability peer client the Authorization Service emits denials to, and
the OIDC token verifier OidcFederationService needs (a real JWKS-fetching
implementation and an in-memory fake for pure business-logic unit tests).
"""
from __future__ import annotations

from typing import Any, Protocol

from identity_and_access.core.domain import (
    AuthDecisionRecord,
    GroupRecord,
    IdentityProviderRecord,
    IdentityRecord,
    IdentityStatus,
    RoleBindingRecord,
    RoleRecord,
    ScimTokenRecord,
)


class IdentityAccessRepository(Protocol):
    async def create_identity(self, record: IdentityRecord) -> IdentityRecord: ...

    async def get_identity(self, identity_id: str) -> IdentityRecord | None: ...

    async def find_identity_by_external_subject(
        self, *, tenant_id: str, provider_id: str, external_subject: str,
    ) -> IdentityRecord | None: ...

    async def update_identity(self, record: IdentityRecord) -> IdentityRecord: ...

    async def list_identities(
        self, *, tenant_id: str | None = None, status: IdentityStatus | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[IdentityRecord], int]: ...

    async def create_role(self, record: RoleRecord) -> RoleRecord: ...

    async def get_role_by_tenant_and_name(self, tenant_id: str, name: str) -> RoleRecord | None:
        """Exact (tenant_id, name) lookup -- no platform-role fallback. Used by
        create_role's own pre-existence check; RoleService.get is the caller
        that wants the tenant-then-platform-fallback resolution instead."""
        ...

    async def get_role(self, tenant_id: str, name: str) -> RoleRecord | None:
        """Resolves a role name the way every real caller (grant, token
        issuance, identity registration) needs it: the calling tenant's own
        role of that name if one exists, else the platform-wide default of
        that name, else None. Never confuse this with
        get_role_by_tenant_and_name's exact lookup."""
        ...

    async def list_roles(
        self, *, tenant_id: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[RoleRecord], int]: ...

    # -- Role bindings (grant/revoke audit trail) --

    async def create_role_binding(self, record: RoleBindingRecord) -> RoleBindingRecord: ...

    async def get_active_role_binding(self, *, identity_id: str, role_name: str) -> RoleBindingRecord | None:
        """The most recent not-yet-revoked binding for this (identity, role)
        pair, if any -- what `revoke` needs to mark revoked."""
        ...

    async def revoke_role_binding(self, binding_id: str) -> RoleBindingRecord | None:
        """Sets revoked_at on this binding row in place -- see
        RoleBindingRecord's own docstring for why revoke is an update to the
        original grant row, not a second row."""
        ...

    async def list_role_bindings(
        self, *, tenant_id: str | None = None, identity_id: str | None = None, role_name: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[RoleBindingRecord], int]: ...

    async def create_auth_decision(self, record: AuthDecisionRecord) -> AuthDecisionRecord: ...

    async def list_auth_decisions(
        self, *, identity_id: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[AuthDecisionRecord], int]: ...

    # -- Identity provider (OIDC/SAML federation config) --

    async def create_identity_provider(self, record: IdentityProviderRecord) -> IdentityProviderRecord: ...

    async def get_identity_provider(self, provider_id: str) -> IdentityProviderRecord | None: ...

    async def list_identity_providers(
        self, *, tenant_id: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[IdentityProviderRecord], int]: ...

    async def update_identity_provider(self, record: IdentityProviderRecord) -> IdentityProviderRecord: ...

    # -- Group (IdP group -> default role mapping) --

    async def create_group(self, record: GroupRecord) -> GroupRecord: ...

    async def get_group(self, group_id: str) -> GroupRecord | None: ...

    async def find_group_by_external_id(
        self, *, tenant_id: str, provider_id: str, external_id: str,
    ) -> GroupRecord | None: ...

    async def list_groups(
        self, *, tenant_id: str | None = None, provider_id: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[GroupRecord], int]: ...

    async def update_group(self, record: GroupRecord) -> GroupRecord: ...

    # -- SCIM provisioning tokens --

    async def create_scim_token(self, record: ScimTokenRecord) -> ScimTokenRecord: ...

    async def get_scim_token_by_hash(self, token_hash: str) -> ScimTokenRecord | None: ...

    async def list_scim_tokens(
        self, *, tenant_id: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[ScimTokenRecord], int]: ...

    async def revoke_scim_token(self, token_id: str) -> ScimTokenRecord | None: ...


class AuditabilityClient(Protocol):
    async def emit(self, event: dict[str, Any]) -> None:
        """Posts to Auditability's own real `POST /v1/auditability/events`.
        Never raises -- a down Auditability peer degrades the audit
        emission, it must never block the auth decision itself."""
        ...


class OidcTokenVerifier(Protocol):
    async def verify(self, *, id_token: str, provider: IdentityProviderRecord) -> dict[str, Any]:
        """Verifies `id_token`'s signature, issuer, and audience against
        `provider`, and returns its decoded claims. Raises
        `core.domain.FederationError` on any failure (bad signature,
        unknown `kid`, expired, wrong issuer/audience) -- callers never
        need to know which JWT-library exception that was."""
        ...


class SamlAssertionVerifier(Protocol):
    async def verify(self, *, saml_response: str, provider: IdentityProviderRecord) -> dict[str, Any]:
        """Verifies a base64-encoded SAMLResponse's XML-DSig signature
        against `provider.x509_certificate`, validates its Conditions
        (NotBefore/NotOnOrAfter) and AudienceRestriction (against
        `provider.client_id`, reused as this SP's expected
        audience/entityID), and returns a claims-shaped dict --
        `{"sub": <NameID>, <attribute Name>: <value or [values]>, ...}` --
        the same shape `OidcTokenVerifier.verify` returns, so
        `core/federation_common.py`'s JIT-provisioning logic and a
        provider's `email_claim`/`groups_claim`/`name_claim` config work
        identically for both protocols. Raises `core.domain.FederationError`
        on any failure (bad signature, expired, wrong audience, missing
        NameID) -- callers never need to know which XML/signxml exception
        that was."""
        ...
