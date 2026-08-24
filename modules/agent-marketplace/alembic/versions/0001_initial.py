"""initial schema: agent_marketplace_listings, agent_marketplace_usage_events

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
        "agent_marketplace_listings",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("agent_card_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("skills_snapshot", pg.JSONB(), nullable=False, server_default="[]"),
        sa.Column("trust_score_snapshot", sa.Float(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending_review"),
        sa.Column("submitted_by", sa.String(255), nullable=False, server_default=""),
        sa.Column("reviewed_by", sa.String(255), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("reuse_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("external_listing_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            onupdate=sa.func.now(), nullable=False,
        ),
    )
    op.create_index("ix_agent_marketplace_listings_tenant", "agent_marketplace_listings", ["tenant_id"])
    op.create_index("ix_agent_marketplace_listings_status", "agent_marketplace_listings", ["status"])

    op.create_table(
        "agent_marketplace_usage_events",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("listing_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("consumer_tenant_id", sa.String(255), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_agent_marketplace_usage_events_listing", "agent_marketplace_usage_events", ["listing_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_marketplace_usage_events_listing", table_name="agent_marketplace_usage_events")
    op.drop_table("agent_marketplace_usage_events")
    op.drop_index("ix_agent_marketplace_listings_status", table_name="agent_marketplace_listings")
    op.drop_index("ix_agent_marketplace_listings_tenant", table_name="agent_marketplace_listings")
    op.drop_table("agent_marketplace_listings")
