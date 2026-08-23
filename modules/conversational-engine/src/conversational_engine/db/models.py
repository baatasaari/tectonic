"""SQLAlchemy 2.0 declarative models for the Conversational Engine data
model (LLD §3.1): ConversationSession, Message, HandoffEvent, PersonaConfig.

IDs are Postgres native `uuid` columns, round-tripping as plain `str` in
Python — same convention as Module 1's db/models.py.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CHAR, JSON, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from conversational_engine.db.base import Base


def _new_id() -> str:
    return str(uuid.uuid4())


JSONType = JSONB().with_variant(JSON(), "sqlite")
UUIDType = UUID(as_uuid=False).with_variant(CHAR(36), "sqlite")


class PersonaConfig(Base):
    __tablename__ = "persona_configs"
    __table_args__ = (Index("ix_persona_configs_tenant", "tenant_id"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    tone_settings: Mapped[dict] = mapped_column(JSONType, default=dict)
    allowed_topics: Mapped[list[str]] = mapped_column(JSONType, default=list)
    denied_topics: Mapped[list[str]] = mapped_column(JSONType, default=list)


class ConversationSession(Base):
    __tablename__ = "conversation_sessions"
    __table_args__ = (
        Index("ix_conversation_sessions_tenant", "tenant_id"),
        Index("ix_conversation_sessions_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    channel: Mapped[str] = mapped_column(String(16))
    user_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active")
    persona_config_ref: Mapped[str] = mapped_column(String(255), default="default")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_activity_at: Mapped[datetime] = mapped_column(server_default=func.now())
    trace_id: Mapped[str] = mapped_column(String(64))

    messages: Mapped[list[Message]] = relationship(back_populates="session")


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_session", "session_id"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    session_id: Mapped[str] = mapped_column(UUIDType, ForeignKey("conversation_sessions.id"))
    direction: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(String())
    emotion_score: Mapped[float | None] = mapped_column(nullable=True)
    guardrail_check_result: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    session: Mapped[ConversationSession] = relationship(back_populates="messages")


class HandoffEvent(Base):
    __tablename__ = "handoff_events"
    __table_args__ = (Index("ix_handoff_events_session", "session_id"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    session_id: Mapped[str] = mapped_column(UUIDType, ForeignKey("conversation_sessions.id"))
    trigger_reason: Mapped[str] = mapped_column(String(32))
    target: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
