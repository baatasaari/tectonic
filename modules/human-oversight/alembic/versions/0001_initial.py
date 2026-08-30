"""initial schema: oversight_requests, decisions, override_records, notification_logs

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
        "oversight_requests",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("requesting_module", sa.String(128), nullable=False),
        sa.Column("requesting_ref", sa.String(255), nullable=False),
        sa.Column("context", pg.JSONB(), nullable=False, server_default="{}"),
        sa.Column("priority", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("claimed_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_oversight_requests_tenant", "oversight_requests", ["tenant_id"])
    op.create_index("ix_oversight_requests_tenant_status", "oversight_requests", ["tenant_id", "status"])

    op.create_table(
        "decisions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("decided_by", sa.String(255), nullable=False),
        sa.Column("decision_reason", sa.String(2048), nullable=False, server_default=""),
        sa.Column("decided_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_decisions_request", "decisions", ["request_id"])

    op.create_table(
        "override_records",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("decision_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("original_agent_proposal", pg.JSONB(), nullable=False, server_default="{}"),
        sa.Column("human_override_action", pg.JSONB(), nullable=False, server_default="{}"),
        sa.Column("override_reason", sa.String(2048), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_override_records_decision", "override_records", ["decision_id"])

    op.create_table(
        "notification_logs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivery_status", sa.String(16), nullable=False, server_default="pending"),
    )
    op.create_index("ix_notification_logs_request", "notification_logs", ["request_id"])


def downgrade() -> None:
    op.drop_index("ix_notification_logs_request", table_name="notification_logs")
    op.drop_table("notification_logs")
    op.drop_index("ix_override_records_decision", table_name="override_records")
    op.drop_table("override_records")
    op.drop_index("ix_decisions_request", table_name="decisions")
    op.drop_table("decisions")
    op.drop_index("ix_oversight_requests_tenant_status", table_name="oversight_requests")
    op.drop_index("ix_oversight_requests_tenant", table_name="oversight_requests")
    op.drop_table("oversight_requests")
