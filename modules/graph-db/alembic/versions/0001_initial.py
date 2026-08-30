"""initial schema: nodes, edges

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
        "nodes",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("entity_type", sa.String(128), nullable=False),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("attributes", pg.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_nodes_tenant", "nodes", ["tenant_id"])

    op.create_table(
        "edges",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("from_node_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("to_node_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("relationship_type", sa.String(128), nullable=False),
        sa.Column("edge_kind", sa.String(16), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("source_ref", sa.String(255), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_edges_tenant_from", "edges", ["tenant_id", "from_node_id"])
    op.create_index("ix_edges_tenant_to", "edges", ["tenant_id", "to_node_id"])


def downgrade() -> None:
    op.drop_index("ix_edges_tenant_to", table_name="edges")
    op.drop_index("ix_edges_tenant_from", table_name="edges")
    op.drop_table("edges")
    op.drop_index("ix_nodes_tenant", table_name="nodes")
    op.drop_table("nodes")
