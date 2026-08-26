"""tenant entitlements: the platform's feature-flag store

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-26

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("entitlements_configured_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "tenant_entitlements",
        sa.Column("tenant_id", sa.String(255), primary_key=True),
        sa.Column("module_name", sa.String(255), primary_key=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            onupdate=sa.func.now(), nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("tenant_entitlements")
    op.drop_column("tenants", "entitlements_configured_at")
