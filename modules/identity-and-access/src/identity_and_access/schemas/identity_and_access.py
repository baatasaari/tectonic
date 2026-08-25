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
