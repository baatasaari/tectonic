"""SQLAlchemy 2.0 declarative models for the Secrets and Credential
Management data model (LLD §3): Secret, SecretVersion, SecretAccess.

`SecretVersion.ciphertext` is the one column in this whole platform that
must never be logged, traced, or included in any API response schema --
see `schemas/secrets_and_credential_management.py` and
`security/envelope_encryption.py`'s own docstrings.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CHAR, Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from secrets_and_credential_management.db.base import Base


def _new_id() -> str:
    return str(uuid.uuid4())


UUIDType = UUID(as_uuid=False).with_variant(CHAR(36), "sqlite")


class Secret(Base):
    __tablename__ = "secrets"

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    namespace: Mapped[str] = mapped_column(String(255))
    key_name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="active")
    rotation_interval_days: Mapped[int] = mapped_column(Integer(), default=90)
    last_rotated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    next_rotation_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    current_version: Mapped[int] = mapped_column(Integer(), default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )


class SecretVersion(Base):
    __tablename__ = "secret_versions"

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    secret_id: Mapped[str] = mapped_column(String(255))
    version: Mapped[int] = mapped_column(Integer())
    ciphertext: Mapped[str] = mapped_column(Text())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SecretAccess(Base):
    __tablename__ = "secret_accesses"

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    secret_id: Mapped[str] = mapped_column(String(255))
    tenant_id: Mapped[str] = mapped_column(String(255))
    allowed: Mapped[bool] = mapped_column(Boolean())
    reason: Mapped[str] = mapped_column(Text())
    accessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
