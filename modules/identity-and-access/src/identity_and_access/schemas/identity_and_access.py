"""Request/response models for `/v1/identity-access/*` (LLD §3)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class CreateRoleRequest(BaseModel):
    name: str
    scopes: list[str]
    description: str = ""


class RoleSchema(BaseModel):
    name: str
    scopes: list[str]
    description: str
    created_at: datetime


class RoleListResponse(BaseModel):
    items: list[RoleSchema]
    total: int
    limit: int
    offset: int


class RegisterIdentityRequest(BaseModel):
    name: str
    type: str = "agent"
    role_names: list[str] = []


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


class IssuedTokenSchema(BaseModel):
    token: str
    granted_scopes: list[str]


class AuthorizeRequest(BaseModel):
    token: str
    required_scope: str


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
    name: str
    provider_type: str
    issuer: str
    client_id: str = ""
    jwks_uri: str = ""
    sso_url: str = ""
    x509_certificate: str = ""
    email_claim: str = "email"
    groups_claim: str = "groups"
    name_claim: str = "name"


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


class RegisterGroupRequest(BaseModel):
    provider_id: str
    external_id: str
    name: str
    default_role_names: list[str] = []


class SetGroupRolesRequest(BaseModel):
    role_names: list[str]


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
