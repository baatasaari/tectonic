"""quota sets, quota counters, resource allocations

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-28

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenant_quota_sets",
        sa.Column("tenant_id", pg.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), primary_key=True),
        sa.Column("limits", pg.JSONB(), nullable=False, server_default="{}"),
        sa.Column("configured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            onupdate=sa.func.now(), nullable=False,
        ),
    )

    op.create_table(
        "quota_counters",
        sa.Column("tenant_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("resource_class", sa.String(128), primary_key=True),
        sa.Column("window_start", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("count", sa.Float(), nullable=False, server_default="0"),
    )

    op.create_table(
        "resource_allocations",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("environment_id", pg.UUID(as_uuid=True), sa.ForeignKey("environments.id"), nullable=False),
        sa.Column("resources", pg.JSONB(), nullable=False, server_default="{}"),
        sa.Column("reserved_capacity", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(16), nullable=False, server_default="requested"),
        sa.Column("requested_by", sa.String(255), nullable=True),
        sa.Column("approved_by", sa.String(255), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            onupdate=sa.func.now(), nullable=False,
        ),
    )
    op.create_index("ix_resource_allocations_environment_id", "resource_allocations", ["environment_id"])


def downgrade() -> None:
    op.drop_index("ix_resource_allocations_environment_id", table_name="resource_allocations")
    op.drop_table("resource_allocations")
    op.drop_table("quota_counters")
    op.drop_table("tenant_quota_sets")
