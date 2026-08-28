"""SQLAlchemy 2.0 declarative model for Vector DB's own migration
bookkeeping (core/domain.py's `MigrationRecord`) -- Qdrant itself is the
real vector data plane and stays outside this ORM entirely (see
core/ports.py's own module docstring).

IDs are Postgres native `uuid` columns but round-trip as plain `str` in
Python (`as_uuid=False`), the same convention every other module in
this platform's own db/models.py already follows.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CHAR, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from vector_db.db.base import Base


def _new_id() -> str:
    return str(uuid.uuid4())


UUIDType = UUID(as_uuid=False).with_variant(CHAR(36), "sqlite")


class Migration(Base):
    __tablename__ = "migrations"

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    source_collection: Mapped[str] = mapped_column(String(255))
    target_collection: Mapped[str] = mapped_column(String(255))
    target_embedding_model: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="running")  # running|completed|failed
    points_total: Mapped[int] = mapped_column(Integer(), default=0)
    points_migrated: Mapped[int] = mapped_column(Integer(), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
