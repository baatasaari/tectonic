"""initial schema: persona_configs, conversation_sessions, messages, handoff_events

Revision ID: 0001
Revises:
Create Date: 2026-08-23

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "persona_configs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("tone_settings", pg.JSONB(), nullable=False, server_default="{}"),
        sa.Column("allowed_topics", pg.JSONB(), nullable=False, server_default="[]"),
        sa.Column("denied_topics", pg.JSONB(), nullable=False, server_default="[]"),
    )
    op.create_index("ix_persona_configs_tenant", "persona_configs", ["tenant_id"])

    op.create_table(
        "conversation_sessions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("user_ref", sa.String(255), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("persona_config_ref", sa.String(255), nullable=False, server_default="default"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("trace_id", sa.String(64), nullable=False),
    )
    op.create_index("ix_conversation_sessions_tenant", "conversation_sessions", ["tenant_id"])
    op.create_index("ix_conversation_sessions_status", "conversation_sessions", ["tenant_id", "status"])

    op.create_table(
        "messages",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", pg.UUID(as_uuid=True), sa.ForeignKey("conversation_sessions.id"), nullable=False),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("emotion_score", sa.Float(), nullable=True),
        sa.Column("guardrail_check_result", pg.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_messages_session", "messages", ["session_id"])

    op.create_table(
        "handoff_events",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", pg.UUID(as_uuid=True), sa.ForeignKey("conversation_sessions.id"), nullable=False),
        sa.Column("trigger_reason", sa.String(32), nullable=False),
        sa.Column("target", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_handoff_events_session", "handoff_events", ["session_id"])


def downgrade() -> None:
    op.drop_table("handoff_events")
    op.drop_table("messages")
    op.drop_index("ix_conversation_sessions_status", table_name="conversation_sessions")
    op.drop_index("ix_conversation_sessions_tenant", table_name="conversation_sessions")
    op.drop_table("conversation_sessions")
    op.drop_index("ix_persona_configs_tenant", table_name="persona_configs")
    op.drop_table("persona_configs")
