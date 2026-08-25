"""SQLAlchemy 2.0 declarative models for the SDK and Developer Portal
data model (LLD §3): DeveloperAccount, ModuleCatalogEntry, SdkPackage.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CHAR, JSON, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from sdk_and_developer_portal.db.base import Base


def _new_id() -> str:
    return str(uuid.uuid4())


UUIDType = UUID(as_uuid=False).with_variant(CHAR(36), "sqlite")


class DeveloperAccount(Base):
    __tablename__ = "developer_accounts"

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255))
    tenant_id: Mapped[str] = mapped_column(String(255))
    identity_id: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )


class ModuleCatalogEntry(Base):
    __tablename__ = "module_catalog_entries"

    module_name: Mapped[str] = mapped_column(String(255), primary_key=True)
    base_url: Mapped[str] = mapped_column(String(512))
    title: Mapped[str] = mapped_column(String(255))
    version: Mapped[str] = mapped_column(String(64))
    path_count: Mapped[int] = mapped_column(Integer())
    spec_json: Mapped[dict] = mapped_column(JSON())
    spec_hash: Mapped[str] = mapped_column(String(64))
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )


class SdkPackage(Base):
    __tablename__ = "sdk_packages"

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    module_name: Mapped[str] = mapped_column(String(255))
    language: Mapped[str] = mapped_column(String(32))
    version: Mapped[int] = mapped_column(Integer())
    source_code: Mapped[str] = mapped_column(Text())
    spec_hash: Mapped[str] = mapped_column(String(64))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
