"""initial schema: agent_cards

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
        "agent_cards",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("agent_ref", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("skills", pg.JSONB(), nullable=False, server_default="[]"),
        sa.Column("trust_score", sa.Float(), nullable=True),
        sa.Column("trust_score_computed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            onupdate=sa.func.now(), nullable=False,
        ),
        sa.UniqueConstraint("tenant_id", "agent_ref", name="uq_agent_cards_tenant_agent_ref"),
    )
    op.create_index("ix_agent_cards_tenant", "agent_cards", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_cards_tenant", table_name="agent_cards")
    op.drop_table("agent_cards")
