"""initial schema: virtual_keys, budget_policies, request_logs, provider_configs

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
        "budget_policies",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("period", sa.String(16), nullable=False),
        sa.Column("limit_amount", sa.Float(), nullable=False),
        sa.Column("current_spend", sa.Float(), nullable=False, server_default="0"),
        sa.Column("alert_threshold_pct", sa.Float(), nullable=False, server_default="0.8"),
    )

    op.create_table(
        "virtual_keys",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("provider_scope", pg.JSONB(), nullable=False, server_default="[]"),
        sa.Column("budget_policy_ref", sa.String(255), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "request_logs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("virtual_key_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost", sa.Float(), nullable=False, server_default="0"),
        sa.Column("cache_hit", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("latency_ms", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_request_logs_tenant", "request_logs", ["tenant_id"])
    op.create_index("ix_request_logs_virtual_key", "request_logs", ["virtual_key_id"])

    op.create_table(
        "provider_configs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider_name", sa.String(64), nullable=False, unique=True),
        sa.Column("endpoint", sa.String(512), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("health_status", sa.String(16), nullable=False, server_default="healthy"),
        sa.Column("deprecation_notices", pg.JSONB(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_table("provider_configs")
    op.drop_index("ix_request_logs_virtual_key", table_name="request_logs")
    op.drop_index("ix_request_logs_tenant", table_name="request_logs")
    op.drop_table("request_logs")
    op.drop_table("virtual_keys")
    op.drop_table("budget_policies")
