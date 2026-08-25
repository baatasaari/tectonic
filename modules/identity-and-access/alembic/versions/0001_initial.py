"""initial schema: identities, roles, auth_decisions

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
        "roles",
        sa.Column("name", sa.String(255), primary_key=True),
        sa.Column("scopes", pg.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "identities",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("type", sa.String(16), nullable=False, server_default="agent"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("role_names", pg.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            onupdate=sa.func.now(), nullable=False,
        ),
    )
    op.create_index("ix_identities_tenant_status", "identities", ["tenant_id", "status"])

    op.create_table(
        "auth_decisions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("identity_id", sa.String(255), nullable=False),
        sa.Column("required_scope", sa.String(255), nullable=False),
        sa.Column("allowed", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_auth_decisions_identity", "auth_decisions", ["identity_id"])


def downgrade() -> None:
    op.drop_index("ix_auth_decisions_identity", table_name="auth_decisions")
    op.drop_table("auth_decisions")
    op.drop_index("ix_identities_tenant_status", table_name="identities")
    op.drop_table("identities")
    op.drop_table("roles")
