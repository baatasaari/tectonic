from __future__ import annotations

import pytest

from identity_and_access.core.authorization_service import AuthorizationService
from identity_and_access.core.fakes import (
    InMemoryIdentityAccessRepository,
    StubAuditabilityClient,
    StubOidcTokenVerifier,
)
from identity_and_access.core.group_service import GroupService
from identity_and_access.core.identity_provider_service import IdentityProviderService
from identity_and_access.core.identity_registry_service import IdentityRegistryService
from identity_and_access.core.oidc_federation_service import OidcFederationService
from identity_and_access.core.role_service import RoleService
from identity_and_access.core.scim_service import ScimGroupService, ScimUserService
from identity_and_access.core.scim_token_service import ScimTokenService
from identity_and_access.core.token_service import TokenService
from identity_and_access.security.token_signer import JWTTokenSigner

SIGNING_SECRET = "test-token-signing-secret-at-least-32-bytes-long"


class Harness:
    def __init__(self, **kwargs):
        self.repository = InMemoryIdentityAccessRepository()
        self.auditability = kwargs.get("auditability") or StubAuditabilityClient()
        self.signer = JWTTokenSigner(signing_secret=kwargs.get("signing_secret", SIGNING_SECRET))
        self.oidc_verifier = kwargs.get("oidc_verifier") or StubOidcTokenVerifier()

        self.identity_registry_service = IdentityRegistryService(self.repository)
        self.role_service = RoleService(self.repository)
        self.token_service = TokenService(
            self.repository, self.signer, default_ttl_seconds=kwargs.get("default_ttl_seconds", 3600),
        )
        self.authorization_service = AuthorizationService(self.repository, self.signer, self.auditability)
        self.identity_provider_service = IdentityProviderService(self.repository)
        self.group_service = GroupService(self.repository)
        self.oidc_federation_service = OidcFederationService(self.repository, self.oidc_verifier)
        self.scim_token_service = ScimTokenService(self.repository)
        self.scim_user_service = ScimUserService(self.repository)
        self.scim_group_service = ScimGroupService(self.repository)


@pytest.fixture
def harness_factory():
    return Harness


@pytest.fixture
def harness():
    return Harness()
