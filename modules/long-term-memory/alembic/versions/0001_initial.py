"""initial schema: memory_items, consolidation_runs, reflection_entries, deletion_records

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
        "memory_items",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("scope", sa.String(255), nullable=False),
        sa.Column("memory_type", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("visibility_policy_ref", sa.String(255), nullable=False, server_default=""),
        sa.Column("vector_ref", sa.String(255), nullable=True),
        sa.Column("graph_ref", sa.String(255), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("relevance_score", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_memory_items_tenant_scope", "memory_items", ["tenant_id", "scope"])
    op.create_index("ix_memory_items_tenant_status", "memory_items", ["tenant_id", "status"])

    op.create_table(
        "consolidation_runs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("items_merged_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("items_decayed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("run_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_consolidation_runs_tenant", "consolidation_runs", ["tenant_id"])

    op.create_table(
        "reflection_entries",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("agent_ref", sa.String(255), nullable=False),
        sa.Column("triggering_interaction_ref", sa.String(255), nullable=False),
        sa.Column("reflection_content", sa.Text(), nullable=False),
        sa.Column("applied", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_reflection_entries_tenant_agent", "reflection_entries", ["tenant_id", "agent_ref"])

    op.create_table(
        "deletion_records",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("subject_ref", sa.String(255), nullable=False),
        sa.Column("memory_items_deleted", pg.JSONB(), nullable=False, server_default="[]"),
        sa.Column("deletion_proof_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("requested_by", sa.String(255), nullable=False, server_default=""),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_deletion_records_tenant", "deletion_records", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_deletion_records_tenant", table_name="deletion_records")
    op.drop_table("deletion_records")
    op.drop_index("ix_reflection_entries_tenant_agent", table_name="reflection_entries")
    op.drop_table("reflection_entries")
    op.drop_index("ix_consolidation_runs_tenant", table_name="consolidation_runs")
    op.drop_table("consolidation_runs")
    op.drop_index("ix_memory_items_tenant_status", table_name="memory_items")
    op.drop_index("ix_memory_items_tenant_scope", table_name="memory_items")
    op.drop_table("memory_items")
