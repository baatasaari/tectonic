"""initial schema: spans

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
        "spans",
        sa.Column("id", sa.String(255), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("span_id", sa.String(64), nullable=False),
        sa.Column("parent_span_id", sa.String(64), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("service_name", sa.String(64), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attributes", pg.JSONB(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(16), nullable=False, server_default="ok"),
        sa.Column("workflow_type", sa.String(64), nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_spans_tenant_trace", "spans", ["tenant_id", "trace_id"])
    op.create_index("ix_spans_tenant_workflow_type", "spans", ["tenant_id", "workflow_type"])


def downgrade() -> None:
    op.drop_index("ix_spans_tenant_workflow_type", table_name="spans")
    op.drop_index("ix_spans_tenant_trace", table_name="spans")
    op.drop_table("spans")
