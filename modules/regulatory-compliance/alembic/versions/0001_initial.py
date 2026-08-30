"""initial schema: framework_profiles, control_mappings, control_implementation_events, evidence_packs

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
        "framework_profiles",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("framework_name", sa.String(64), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_framework_profiles_tenant", "framework_profiles", ["tenant_id"])

    op.create_table(
        "control_mappings",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("control_name", sa.String(128), nullable=False),
        sa.Column("framework_name", sa.String(64), nullable=False),
        sa.Column("framework_version", sa.String(32), nullable=False),
        sa.Column("clause_references", pg.JSONB(), nullable=False, server_default="[]"),
        sa.Column("mapping_rationale", sa.Text(), nullable=False),
        sa.Column("deprecated", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.create_index("ix_control_mappings_control_framework", "control_mappings", ["control_name", "framework_name"])

    op.create_table(
        "control_implementation_events",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("control_name", sa.String(128), nullable=False),
        sa.Column("source_module", sa.String(64), nullable=False),
        sa.Column("evidence_ref", sa.String(255), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_control_events_tenant", "control_implementation_events", ["tenant_id"])

    op.create_table(
        "evidence_packs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("framework_name", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="requested"),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("coverage_percentage", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("document_ref", sa.String(255), nullable=True),
        sa.Column("document_format", sa.String(8), nullable=False, server_default="pdf"),
        sa.Column("document_bytes_b64", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_evidence_packs_tenant", "evidence_packs", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_evidence_packs_tenant", table_name="evidence_packs")
    op.drop_table("evidence_packs")
    op.drop_index("ix_control_events_tenant", table_name="control_implementation_events")
    op.drop_table("control_implementation_events")
    op.drop_index("ix_control_mappings_control_framework", table_name="control_mappings")
    op.drop_table("control_mappings")
    op.drop_index("ix_framework_profiles_tenant", table_name="framework_profiles")
    op.drop_table("framework_profiles")
