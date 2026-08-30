"""initial schema: extractions

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
        "extractions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("modality", sa.String(16), nullable=False),
        sa.Column("raw_content", sa.Text(), nullable=False),
        sa.Column("extracted_content", sa.Text(), nullable=False),
        sa.Column("grounding_context", sa.Text(), nullable=True),
        sa.Column("groundedness_decision", sa.String(16), nullable=False, server_default="not_checked"),
        sa.Column("groundedness_violation_category", sa.String(64), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_extractions_tenant_modality", "extractions", ["tenant_id", "modality"])


def downgrade() -> None:
    op.drop_index("ix_extractions_tenant_modality", table_name="extractions")
    op.drop_table("extractions")
