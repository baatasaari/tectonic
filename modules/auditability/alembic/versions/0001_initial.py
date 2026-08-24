"""initial schema: audit_events, audit_packs

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
        "audit_events",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("source_module", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("payload", pg.JSONB(), nullable=False, server_default="{}"),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("prev_hash", sa.String(64), nullable=True),
        sa.Column("entry_hash", sa.String(64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "sequence_number", name="uq_audit_events_tenant_sequence"),
    )
    op.create_index("ix_audit_events_tenant_sequence", "audit_events", ["tenant_id", "sequence_number"])
    op.create_index("ix_audit_events_tenant_event_type", "audit_events", ["tenant_id", "event_type"])
    op.create_index("ix_audit_events_tenant_source_module", "audit_events", ["tenant_id", "source_module"])

    op.create_table(
        "audit_packs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="requested"),
        sa.Column("filter_event_type", sa.String(128), nullable=True),
        sa.Column("filter_source_module", sa.String(64), nullable=True),
        sa.Column("filter_control_name", sa.String(128), nullable=True),
        sa.Column("filter_occurred_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("filter_occurred_before", sa.DateTime(timezone=True), nullable=True),
        sa.Column("event_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("chain_valid", sa.Boolean(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("document_ref", sa.String(255), nullable=True),
        sa.Column("document_format", sa.String(8), nullable=False, server_default="pdf"),
        sa.Column("document_bytes_b64", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("worker_id", sa.String(64), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
    )
    op.create_index("ix_audit_packs_tenant", "audit_packs", ["tenant_id"])
    op.create_index("ix_audit_packs_status_lease", "audit_packs", ["status", "lease_expires_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_packs_status_lease", table_name="audit_packs")
    op.drop_index("ix_audit_packs_tenant", table_name="audit_packs")
    op.drop_table("audit_packs")
    op.drop_index("ix_audit_events_tenant_source_module", table_name="audit_events")
    op.drop_index("ix_audit_events_tenant_event_type", table_name="audit_events")
    op.drop_index("ix_audit_events_tenant_sequence", table_name="audit_events")
    op.drop_table("audit_events")
