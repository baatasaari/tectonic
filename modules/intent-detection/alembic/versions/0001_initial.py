"""initial schema: intent_taxonomies, classification_logs, drift_reports

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
        "intent_taxonomies",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("intents", pg.JSONB(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_intent_taxonomies_tenant_version", "intent_taxonomies", ["tenant_id", "version"], unique=True)

    op.create_table(
        "classification_logs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("taxonomy_version", sa.Integer(), nullable=False),
        sa.Column("intents_detected", pg.JSONB(), nullable=False, server_default="[]"),
        sa.Column("fallback_used", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_classification_logs_tenant", "classification_logs", ["tenant_id"])

    op.create_table(
        "drift_reports",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("taxonomy_version", sa.Integer(), nullable=False),
        sa.Column("drift_score", sa.Float(), nullable=False),
        sa.Column("flagged_intents", pg.JSONB(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_drift_reports_tenant", "drift_reports", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("drift_reports")
    op.drop_index("ix_classification_logs_tenant", table_name="classification_logs")
    op.drop_table("classification_logs")
    op.drop_index("ix_intent_taxonomies_tenant_version", table_name="intent_taxonomies")
    op.drop_table("intent_taxonomies")
