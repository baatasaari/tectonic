"""SQLAlchemy 2.0 declarative models for the Identity and Access module
data model (LLD §3, extended for OIDC/SAML federation + SCIM): Identity,
Role, AuthDecision, IdentityProvider, Group, ScimToken.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CHAR, JSON, Boolean, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from identity_and_access.db.base import Base


def _new_id() -> str:
    return str(uuid.uuid4())


UUIDType = UUID(as_uuid=False).with_variant(CHAR(36), "sqlite")
# ARRAY(String) has no SQLite equivalent; a JSON-backed variant keeps the unit tier
# honest without needing a real Postgres array type there.
StringArray = ARRAY(String).with_variant(JSON(), "sqlite")


class Identity(Base):
    __tablename__ = "identities"

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    type: Mapped[str] = mapped_column(String(16), default="agent")
    status: Mapped[str] = mapped_column(String(16), default="active")
    role_names: Mapped[list[str]] = mapped_column(StringArray, default=list)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    external_provider_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    federated_role_names: Mapped[list[str]] = mapped_column(StringArray, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )


class Role(Base):
    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(255), primary_key=True)
    scopes: Mapped[list[str]] = mapped_column(StringArray, default=list)
    description: Mapped[str] = mapped_column(Text(), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuthDecision(Base):
    __tablename__ = "auth_decisions"

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    identity_id: Mapped[str] = mapped_column(String(255))
    required_scope: Mapped[str] = mapped_column(String(255))
    allowed: Mapped[bool] = mapped_column(Boolean())
    reason: Mapped[str] = mapped_column(Text())
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IdentityProvider(Base):
    __tablename__ = "identity_providers"

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    provider_type: Mapped[str] = mapped_column(String(16))
    issuer: Mapped[str] = mapped_column(String(500))
    enabled: Mapped[bool] = mapped_column(Boolean(), default=True)
    client_id: Mapped[str] = mapped_column(String(255), default="")
    jwks_uri: Mapped[str] = mapped_column(String(500), default="")
    sso_url: Mapped[str] = mapped_column(String(500), default="")
    x509_certificate: Mapped[str] = mapped_column(Text(), default="")
    email_claim: Mapped[str] = mapped_column(String(100), default="email")
    groups_claim: Mapped[str] = mapped_column(String(100), default="groups")
    name_claim: Mapped[str] = mapped_column(String(100), default="name")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    provider_id: Mapped[str] = mapped_column(String(255))
    external_id: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    default_role_names: Mapped[list[str]] = mapped_column(StringArray, default=list)
    member_identity_ids: Mapped[list[str]] = mapped_column(StringArray, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ScimToken(Base):
    __tablename__ = "scim_tokens"

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    token_hash: Mapped[str] = mapped_column(String(64))
    revoked: Mapped[bool] = mapped_column(Boolean(), default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
