"""Memory governance foundation: consent_records, legal_holds tables,
and a new memory_items.purpose column.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-30

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("memory_items", sa.Column("purpose", sa.String(255), nullable=False, server_default=""))

    op.create_table(
        "consent_records",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("scope", sa.String(255), nullable=False),
        sa.Column("purpose", sa.String(255), nullable=False),
        sa.Column("basis", sa.String(32), nullable=False),
        sa.Column("granted_by", sa.String(255), nullable=False, server_default=""),
        sa.Column("granted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_consent_records_tenant_scope_purpose", "consent_records", ["tenant_id", "scope", "purpose"],
    )

    op.create_table(
        "legal_holds",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("scope", sa.String(255), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("placed_by", sa.String(255), nullable=False, server_default=""),
        sa.Column("placed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_legal_holds_tenant_scope", "legal_holds", ["tenant_id", "scope"])


def downgrade() -> None:
    op.drop_index("ix_legal_holds_tenant_scope", table_name="legal_holds")
    op.drop_table("legal_holds")
    op.drop_index("ix_consent_records_tenant_scope_purpose", table_name="consent_records")
    op.drop_table("consent_records")
    op.drop_column("memory_items", "purpose")
