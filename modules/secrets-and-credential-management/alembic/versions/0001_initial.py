"""initial schema: secrets, secret_versions, secret_accesses

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
        "secrets",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("namespace", sa.String(255), nullable=False),
        sa.Column("key_name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("rotation_interval_days", sa.Integer(), nullable=False, server_default="90"),
        sa.Column("last_rotated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("next_rotation_due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            onupdate=sa.func.now(), nullable=False,
        ),
    )
    op.create_index("ix_secrets_tenant_namespace_status", "secrets", ["tenant_id", "namespace", "status"])
    op.create_index("ix_secrets_next_rotation_due", "secrets", ["status", "next_rotation_due_at"])

    op.create_table(
        "secret_versions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("secret_id", sa.String(255), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("ciphertext", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_secret_versions_secret_version", "secret_versions", ["secret_id", "version"])

    op.create_table(
        "secret_accesses",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("secret_id", sa.String(255), nullable=False),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("allowed", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("accessed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_secret_accesses_secret", "secret_accesses", ["secret_id"])


def downgrade() -> None:
    op.drop_index("ix_secret_accesses_secret", table_name="secret_accesses")
    op.drop_table("secret_accesses")
    op.drop_index("ix_secret_versions_secret_version", table_name="secret_versions")
    op.drop_table("secret_versions")
    op.drop_index("ix_secrets_next_rotation_due", table_name="secrets")
    op.drop_index("ix_secrets_tenant_namespace_status", table_name="secrets")
    op.drop_table("secrets")
