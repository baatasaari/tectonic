"""initial schema: tool_definitions, tool_invocations, reliability_scores

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
        "tool_definitions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("mcp_server_ref", sa.String(255), nullable=False),
        sa.Column("schema", pg.JSONB(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("synthesised", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_tool_definitions_tenant", "tool_definitions", ["tenant_id"])

    op.create_table(
        "tool_invocations",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tool_id", pg.UUID(as_uuid=True), sa.ForeignKey("tool_definitions.id"), nullable=False),
        sa.Column("agent_ref", sa.String(255), nullable=False),
        sa.Column("workflow_instance_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_tool_invocations_tool", "tool_invocations", ["tool_id"])

    op.create_table(
        "reliability_scores",
        sa.Column("tool_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("rolling_success_rate", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("rolling_avg_latency_ms", sa.Float(), nullable=False, server_default="0"),
        sa.Column("last_updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("reliability_scores")
    op.drop_index("ix_tool_invocations_tool", table_name="tool_invocations")
    op.drop_table("tool_invocations")
    op.drop_index("ix_tool_definitions_tenant", table_name="tool_definitions")
    op.drop_table("tool_definitions")
