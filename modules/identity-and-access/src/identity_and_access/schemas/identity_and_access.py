"""Request/response models for `/v1/identity-access/*` (LLD §3)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, field_validator

from identity_and_access.core.domain import IdentityProviderType, IdentityType


def _reject_null_byte(value: str) -> str:
    """Postgres's `text`/`varchar`/`json` columns are UTF-8 and reject the
    NUL byte outright (`asyncpg.exceptions.CharacterNotInRepertoireError`)
    -- a value `str` is happy to hold but the database is not. Schema-
    valid per OpenAPI (`type: string` says nothing about NUL), so
    nothing upstream of the DB call rejects it without this: caught
    here as a clean `422` instead of the request reaching the database
    at all (found by this module's own brand-new OpenAPI contract-test
    tier's very first run -- the same fix Multi-tenancy's, Billing and
    Metering's, and LLM Gateway's own `_reject_null_byte` already
    established; ticket #82's platform-wide sweep never covered this
    module's own body fields since this module had no contract tier at
    the time)."""
    if "\x00" in value:
        raise ValueError("must not contain a NUL byte (unsupported by Postgres's text encoding)")
    return value


class CreateRoleRequest(BaseModel):
    name: str
    scopes: list[str]
    description: str = ""

    @field_validator("name", "description")
    @classmethod
    def _validate_no_null_byte(cls, value: str) -> str:
        return _reject_null_byte(value)

    @field_validator("scopes")
    @classmethod
    def _validate_scopes(cls, value: list[str]) -> list[str]:
        for item in value:
            _reject_null_byte(item)
        return value


class RoleSchema(BaseModel):
    id: str
    tenant_id: str
    name: str
    scopes: list[str]
    description: str
    created_at: datetime


class RoleListResponse(BaseModel):
    items: list[RoleSchema]
    total: int
    limit: int
    offset: int


class GrantRoleRequest(BaseModel):
    role_name: str
    granted_by: str = ""

    @field_validator("role_name", "granted_by")
    @classmethod
    def _validate_no_null_byte(cls, value: str) -> str:
        return _reject_null_byte(value)


class RoleBindingSchema(BaseModel):
    id: str
    tenant_id: str
    identity_id: str
    role_name: str
    granted_by: str
    granted_at: datetime
    revoked_at: datetime | None = None


class RoleBindingListResponse(BaseModel):
    items: list[RoleBindingSchema]
    total: int
    limit: int
    offset: int


class RegisterIdentityRequest(BaseModel):
    """`type` is typed as the real `IdentityType` enum, not a bare `str`
    hand-converted at the route -- ticket #82's own sibling bug class
    (an invalid value raising an unhandled `ValueError`/500 instead of a
    clean 422), found here by this module's own OpenAPI contract-test
    tier."""

    name: str
    type: IdentityType = IdentityType.AGENT
    role_names: list[str] = []

    @field_validator("name")
    @classmethod
    def _validate_no_null_byte(cls, value: str) -> str:
        return _reject_null_byte(value)

    @field_validator("role_names")
    @classmethod
    def _validate_role_names(cls, value: list[str]) -> list[str]:
        for item in value:
            _reject_null_byte(item)
        return value


class IdentitySchema(BaseModel):
    id: str
    tenant_id: str
    name: str
    type: str
    status: str
    role_names: list[str]
    email: str | None = None
    external_provider_id: str | None = None
    external_subject: str | None = None
    federated_role_names: list[str] = []
    created_at: datetime
    updated_at: datetime


class IdentityListResponse(BaseModel):
    items: list[IdentitySchema]
    total: int
    limit: int
    offset: int


class IssueTokenRequest(BaseModel):
    identity_id: str
    requested_scopes: list[str] | None = None
    ttl_seconds: int | None = None

    @field_validator("identity_id")
    @classmethod
    def _validate_no_null_byte(cls, value: str) -> str:
        return _reject_null_byte(value)


class IssuedTokenSchema(BaseModel):
    token: str
    granted_scopes: list[str]


class AuthorizeRequest(BaseModel):
    token: str
    required_scope: str

    @field_validator("required_scope")
    @classmethod
    def _validate_no_null_byte(cls, value: str) -> str:
        # `token`'s NUL bytes never reach the database directly -- it's decoded via
        # JWT verification first, and only the decoded claims/a canned failure reason
        # are ever persisted, not the raw token string. `required_scope` is different:
        # AuthorizationService.authorize persists it verbatim into AuthDecisionRecord
        # (the audit trail) on every call, allowed or denied -- found by this
        # module's own OpenAPI contract-test tier.
        return _reject_null_byte(value)


class AuthDecisionResultSchema(BaseModel):
    allowed: bool
    reason: str


class AuthDecisionSchema(BaseModel):
    id: str
    tenant_id: str
    identity_id: str
    required_scope: str
    allowed: bool
    reason: str
    checked_at: datetime


class AuthDecisionListResponse(BaseModel):
    items: list[AuthDecisionSchema]
    total: int
    limit: int
    offset: int


class RegisterIdentityProviderRequest(BaseModel):
    """`provider_type` is typed as the real `IdentityProviderType` enum
    for the same reason `RegisterIdentityRequest.type` is -- see that
    model's own docstring."""

    name: str
    provider_type: IdentityProviderType
    issuer: str
    client_id: str = ""
    jwks_uri: str = ""
    sso_url: str = ""
    x509_certificate: str = ""
    email_claim: str = "email"
    groups_claim: str = "groups"
    name_claim: str = "name"

    @field_validator(
        "name", "issuer", "client_id", "jwks_uri", "sso_url", "x509_certificate",
        "email_claim", "groups_claim", "name_claim",
    )
    @classmethod
    def _validate_no_null_byte(cls, value: str) -> str:
        return _reject_null_byte(value)


class IdentityProviderSchema(BaseModel):
    id: str
    tenant_id: str
    name: str
    provider_type: str
    issuer: str
    enabled: bool
    client_id: str
    jwks_uri: str
    sso_url: str
    # x509_certificate is deliberately omitted here -- read back via a dedicated
    # endpoint only if this module ever needs to expose it, not by default in every
    # listing (the same posture Secrets and Credential Management takes with
    # never echoing a secret's material back in a generic list response).
    email_claim: str
    groups_claim: str
    name_claim: str
    created_at: datetime
    updated_at: datetime


class IdentityProviderListResponse(BaseModel):
    items: list[IdentityProviderSchema]
    total: int
    limit: int
    offset: int


class OidcLoginRequest(BaseModel):
    provider_id: str
    id_token: str

    @field_validator("provider_id")
    @classmethod
    def _validate_no_null_byte(cls, value: str) -> str:
        return _reject_null_byte(value)


class SamlLoginRequest(BaseModel):
    provider_id: str
    # The real SAML HTTP-POST binding's SAMLResponse form field: base64-encoded XML,
    # verified for real by security/saml_verifier.py -- see that module's docstring.
    saml_response: str

    @field_validator("provider_id")
    @classmethod
    def _validate_no_null_byte(cls, value: str) -> str:
        return _reject_null_byte(value)


class RegisterGroupRequest(BaseModel):
    provider_id: str
    external_id: str
    name: str
    default_role_names: list[str] = []

    @field_validator("provider_id", "external_id", "name")
    @classmethod
    def _validate_no_null_byte(cls, value: str) -> str:
        return _reject_null_byte(value)

    @field_validator("default_role_names")
    @classmethod
    def _validate_default_role_names(cls, value: list[str]) -> list[str]:
        for item in value:
            _reject_null_byte(item)
        return value


class SetGroupRolesRequest(BaseModel):
    role_names: list[str]

    @field_validator("role_names")
    @classmethod
    def _validate_role_names(cls, value: list[str]) -> list[str]:
        for item in value:
            _reject_null_byte(item)
        return value


class GroupSchema(BaseModel):
    id: str
    tenant_id: str
    provider_id: str
    external_id: str
    name: str
    default_role_names: list[str]
    created_at: datetime


class GroupListResponse(BaseModel):
    items: list[GroupSchema]
    total: int
    limit: int
    offset: int


class CreateScimTokenRequest(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def _validate_no_null_byte(cls, value: str) -> str:
        return _reject_null_byte(value)


class ScimTokenCreatedSchema(BaseModel):
    id: str
    tenant_id: str
    name: str
    token: str  # cleartext -- shown exactly once, at creation
    created_at: datetime


class ScimTokenSchema(BaseModel):
    id: str
    tenant_id: str
    name: str
    revoked: bool
    created_at: datetime


class ScimTokenListResponse(BaseModel):
    items: list[ScimTokenSchema]
    total: int
    limit: int
    offset: int
