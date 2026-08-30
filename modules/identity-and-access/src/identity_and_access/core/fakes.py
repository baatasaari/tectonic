"""In-memory fakes for unit tests (LLD "Deployability and testability
contract"). `JWTTokenSigner` needs no fake -- see its own docstring --
so only the repository, the real Auditability peer client, and the real
OIDC JWKS-fetching verifier are faked here.
"""
from __future__ import annotations

from typing import Any

from identity_and_access.core.domain import (
    AuthDecisionRecord,
    FederationError,
    GroupRecord,
    IdentityProviderRecord,
    IdentityRecord,
    IdentityStatus,
    RoleRecord,
    ScimTokenRecord,
)


class InMemoryIdentityAccessRepository:
    def __init__(self) -> None:
        self.identities: dict[str, IdentityRecord] = {}
        self.roles: dict[str, RoleRecord] = {}
        self.auth_decisions: list[AuthDecisionRecord] = []
        self.identity_providers: dict[str, IdentityProviderRecord] = {}
        self.groups: dict[str, GroupRecord] = {}
        self.scim_tokens: dict[str, ScimTokenRecord] = {}

    async def create_identity(self, record: IdentityRecord) -> IdentityRecord:
        self.identities[record.id] = record
        return record

    async def get_identity(self, identity_id: str) -> IdentityRecord | None:
        return self.identities.get(identity_id)

    async def find_identity_by_external_subject(
        self, *, tenant_id: str, provider_id: str, external_subject: str,
    ) -> IdentityRecord | None:
        for identity in self.identities.values():
            if (
                identity.tenant_id == tenant_id
                and identity.external_provider_id == provider_id
                and identity.external_subject == external_subject
            ):
                return identity
        return None

    async def update_identity(self, record: IdentityRecord) -> IdentityRecord:
        self.identities[record.id] = record
        return record

    async def list_identities(
        self, *, tenant_id: str | None = None, status: IdentityStatus | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[IdentityRecord], int]:
        results = list(self.identities.values())
        if tenant_id is not None:
            results = [i for i in results if i.tenant_id == tenant_id]
        if status is not None:
            results = [i for i in results if i.status == status]
        results = sorted(results, key=lambda i: i.created_at)
        return results[offset:offset + limit], len(results)

    async def create_role(self, record: RoleRecord) -> RoleRecord:
        self.roles[record.name] = record
        return record

    async def get_role(self, name: str) -> RoleRecord | None:
        return self.roles.get(name)

    async def list_roles(self, *, limit: int = 50, offset: int = 0) -> tuple[list[RoleRecord], int]:
        results = sorted(self.roles.values(), key=lambda r: r.created_at)
        return results[offset:offset + limit], len(results)

    async def create_auth_decision(self, record: AuthDecisionRecord) -> AuthDecisionRecord:
        self.auth_decisions.append(record)
        return record

    async def list_auth_decisions(
        self, *, identity_id: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[AuthDecisionRecord], int]:
        results = list(self.auth_decisions)
        if identity_id is not None:
            results = [d for d in results if d.identity_id == identity_id]
        results = sorted(results, key=lambda d: d.checked_at, reverse=True)
        return results[offset:offset + limit], len(results)

    async def create_identity_provider(self, record: IdentityProviderRecord) -> IdentityProviderRecord:
        self.identity_providers[record.id] = record
        return record

    async def get_identity_provider(self, provider_id: str) -> IdentityProviderRecord | None:
        return self.identity_providers.get(provider_id)

    async def list_identity_providers(
        self, *, tenant_id: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[IdentityProviderRecord], int]:
        results = list(self.identity_providers.values())
        if tenant_id is not None:
            results = [p for p in results if p.tenant_id == tenant_id]
        results = sorted(results, key=lambda p: p.created_at)
        return results[offset:offset + limit], len(results)

    async def update_identity_provider(self, record: IdentityProviderRecord) -> IdentityProviderRecord:
        self.identity_providers[record.id] = record
        return record

    async def create_group(self, record: GroupRecord) -> GroupRecord:
        self.groups[record.id] = record
        return record

    async def get_group(self, group_id: str) -> GroupRecord | None:
        return self.groups.get(group_id)

    async def find_group_by_external_id(
        self, *, tenant_id: str, provider_id: str, external_id: str,
    ) -> GroupRecord | None:
        for group in self.groups.values():
            if group.tenant_id == tenant_id and group.provider_id == provider_id and group.external_id == external_id:
                return group
        return None

    async def list_groups(
        self, *, tenant_id: str | None = None, provider_id: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[GroupRecord], int]:
        results = list(self.groups.values())
        if tenant_id is not None:
            results = [g for g in results if g.tenant_id == tenant_id]
        if provider_id is not None:
            results = [g for g in results if g.provider_id == provider_id]
        results = sorted(results, key=lambda g: g.created_at)
        return results[offset:offset + limit], len(results)

    async def update_group(self, record: GroupRecord) -> GroupRecord:
        self.groups[record.id] = record
        return record

    async def create_scim_token(self, record: ScimTokenRecord) -> ScimTokenRecord:
        self.scim_tokens[record.id] = record
        return record

    async def get_scim_token_by_hash(self, token_hash: str) -> ScimTokenRecord | None:
        for token in self.scim_tokens.values():
            if token.token_hash == token_hash:
                return token
        return None

    async def list_scim_tokens(
        self, *, tenant_id: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[ScimTokenRecord], int]:
        results = list(self.scim_tokens.values())
        if tenant_id is not None:
            results = [t for t in results if t.tenant_id == tenant_id]
        results = sorted(results, key=lambda t: t.created_at)
        return results[offset:offset + limit], len(results)

    async def revoke_scim_token(self, token_id: str) -> ScimTokenRecord | None:
        token = self.scim_tokens.get(token_id)
        if token is None:
            return None
        token.revoked = True
        return token


class StubAuditabilityClient:
    def __init__(self, *, raise_error: bool = False) -> None:
        self.events: list[dict[str, Any]] = []
        self._raise_error = raise_error

    async def emit(self, event: dict[str, Any]) -> None:
        if self._raise_error:
            raise RuntimeError("auditability is down")
        self.events.append(event)


class StubOidcTokenVerifier:
    """No network, no JWKS -- a canned claims dict per `id_token` string
    value, keyed exactly, for pure OidcFederationService business-logic
    tests. `HTTPOidcTokenVerifier` (security/oidc_verifier.py) is the real
    thing; see tests/unit/test_oidc_federation_service.py for the one real
    RS256-signed-token, respx-mocked-JWKS end-to-end test that exercises it
    instead of this stub."""

    def __init__(self) -> None:
        self.claims_by_token: dict[str, dict[str, Any]] = {}

    async def verify(self, *, id_token: str, provider: IdentityProviderRecord) -> dict[str, Any]:
        claims = self.claims_by_token.get(id_token)
        if claims is None:
            raise FederationError("unknown or invalid id_token")
        return claims


class StubSamlAssertionVerifier:
    """No XML, no XML-DSig -- a canned claims dict per `saml_response`
    string value, keyed exactly, for pure SamlFederationService
    business-logic tests. `XmlDsigSamlAssertionVerifier`
    (security/saml_verifier.py) is the real thing; see
    tests/unit/test_saml_verifier.py for the real-signed-XML,
    real-signxml-verification end-to-end tests that exercise it instead
    of this stub."""

    def __init__(self) -> None:
        self.claims_by_response: dict[str, dict[str, Any]] = {}

    async def verify(self, *, saml_response: str, provider: IdentityProviderRecord) -> dict[str, Any]:
        claims = self.claims_by_response.get(saml_response)
        if claims is None:
            raise FederationError("unknown or invalid saml_response")
        return claims


__all__ = [
    "InMemoryIdentityAccessRepository",
    "StubAuditabilityClient",
    "StubOidcTokenVerifier",
    "StubSamlAssertionVerifier",
]
