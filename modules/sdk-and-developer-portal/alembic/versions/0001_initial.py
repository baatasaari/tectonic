"""initial schema: developer_accounts, module_catalog_entries, sdk_packages

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
        "developer_accounts",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("identity_id", sa.String(255), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            onupdate=sa.func.now(), nullable=False,
        ),
    )
    op.create_index("ix_developer_accounts_status", "developer_accounts", ["status"])

    op.create_table(
        "module_catalog_entries",
        sa.Column("module_name", sa.String(255), primary_key=True),
        sa.Column("base_url", sa.String(512), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("path_count", sa.Integer(), nullable=False),
        sa.Column("spec_json", pg.JSON(), nullable=False),
        sa.Column("spec_hash", sa.String(64), nullable=False),
        sa.Column(
            "last_synced_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            onupdate=sa.func.now(), nullable=False,
        ),
    )

    op.create_table(
        "sdk_packages",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("module_name", sa.String(255), nullable=False),
        sa.Column("language", sa.String(32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("source_code", sa.Text(), nullable=False),
        sa.Column("spec_hash", sa.String(64), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_sdk_packages_module_language", "sdk_packages", ["module_name", "language"])


def downgrade() -> None:
    op.drop_index("ix_sdk_packages_module_language", table_name="sdk_packages")
    op.drop_table("sdk_packages")
    op.drop_table("module_catalog_entries")
    op.drop_index("ix_developer_accounts_status", table_name="developer_accounts")
    op.drop_table("developer_accounts")
