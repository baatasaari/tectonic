"""initial schema: a2a_tasks, a2a_access_policies, agent_card_cache

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
        "a2a_tasks",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("peer_agent_url", sa.String(2048), nullable=False),
        sa.Column("skill_id", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="submitted"),
        sa.Column("input_message", pg.JSONB(), nullable=False, server_default="{}"),
        sa.Column("output_artifacts", pg.JSONB(), nullable=False, server_default="[]"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            onupdate=sa.func.now(), nullable=False,
        ),
    )
    op.create_index("ix_a2a_tasks_tenant", "a2a_tasks", ["tenant_id"])
    op.create_index("ix_a2a_tasks_direction", "a2a_tasks", ["direction"])

    op.create_table(
        "a2a_access_policies",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("caller_agent_id", sa.String(255), nullable=False),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("allowed_skills", pg.JSONB(), nullable=True),
        sa.UniqueConstraint("caller_agent_id", "tenant_id", name="uq_a2a_access_policies_caller_tenant"),
    )
    op.create_index("ix_a2a_access_policies_caller_tenant", "a2a_access_policies", ["caller_agent_id", "tenant_id"])

    op.create_table(
        "agent_card_cache",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("agent_url", sa.String(2048), nullable=False),
        sa.Column("card", pg.JSONB(), nullable=False, server_default="{}"),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("agent_url", name="uq_agent_card_cache_agent_url"),
    )


def downgrade() -> None:
    op.drop_table("agent_card_cache")
    op.drop_index("ix_a2a_access_policies_caller_tenant", table_name="a2a_access_policies")
    op.drop_table("a2a_access_policies")
    op.drop_index("ix_a2a_tasks_direction", table_name="a2a_tasks")
    op.drop_index("ix_a2a_tasks_tenant", table_name="a2a_tasks")
    op.drop_table("a2a_tasks")
