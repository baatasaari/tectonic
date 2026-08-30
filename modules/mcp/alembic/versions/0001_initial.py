"""initial schema: mcp_servers, mcp_tools, access_policies

Revision ID: 0001
Revises:
Create Date: 2026-08-24

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
        "mcp_servers",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("base_url", sa.String(2048), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_mcp_servers_tenant", "mcp_servers", ["tenant_id"])

    op.create_table(
        "mcp_tools",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("server_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("input_schema", pg.JSONB(), nullable=False, server_default="{}"),
        sa.Column("synced_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_mcp_tools_server", "mcp_tools", ["server_id"])

    op.create_table(
        "access_policies",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("server_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("allowed_tools", pg.JSONB(), nullable=True),
        sa.UniqueConstraint("server_id", "tenant_id", name="uq_access_policies_server_tenant"),
    )
    op.create_index("ix_access_policies_server_tenant", "access_policies", ["server_id", "tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_access_policies_server_tenant", table_name="access_policies")
    op.drop_table("access_policies")
    op.drop_index("ix_mcp_tools_server", table_name="mcp_tools")
    op.drop_table("mcp_tools")
    op.drop_index("ix_mcp_servers_tenant", table_name="mcp_servers")
    op.drop_table("mcp_servers")
