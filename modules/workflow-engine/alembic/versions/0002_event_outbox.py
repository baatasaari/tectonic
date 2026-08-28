"""transactional event outbox

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-28

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
    op.create_table(
        "event_outbox",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("topic", sa.String(128), nullable=False),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("envelope", pg.JSONB(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("worker_id", sa.String(64), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_event_outbox_status_lease", "event_outbox", ["status", "lease_expires_at"])


def downgrade() -> None:
    op.drop_index("ix_event_outbox_status_lease", table_name="event_outbox")
    op.drop_table("event_outbox")
