"""initial schema: deployments

Revision ID: 0001
Revises:
Create Date: 2026-08-25

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
        "deployments",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("service_name", sa.String(255), nullable=False),
        sa.Column("build_ref", sa.String(255), nullable=False),
        sa.Column("target", sa.String(255), nullable=False),
        sa.Column("canary_percentage", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("budget_policy_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("stage", sa.String(32), nullable=False, server_default="canary"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rolled_back_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rollback_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            onupdate=sa.func.now(), nullable=False,
        ),
    )
    op.create_index("ix_deployments_tenant_service_target", "deployments", ["tenant_id", "service_name", "target"])
    op.create_index("ix_deployments_stage", "deployments", ["stage"])


def downgrade() -> None:
    op.drop_index("ix_deployments_stage", table_name="deployments")
    op.drop_index("ix_deployments_tenant_service_target", table_name="deployments")
    op.drop_table("deployments")
