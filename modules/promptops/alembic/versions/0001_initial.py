"""initial schema: prompt_versions, ab_tests

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
        "prompt_versions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("prompt_name", sa.String(255), nullable=False),
        sa.Column("version", sa.String(255), nullable=False),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("parent_version_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("promoted_pass_rate", sa.Float(), nullable=True),
        sa.Column("promoted_sample_size", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            onupdate=sa.func.now(), nullable=False,
        ),
    )
    op.create_index("ix_prompt_versions_tenant_name", "prompt_versions", ["tenant_id", "prompt_name"])

    op.create_table(
        "ab_tests",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("prompt_name", sa.String(255), nullable=False),
        sa.Column("version_a_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("version_b_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
        sa.Column("winner_version_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("p_value", sa.Float(), nullable=True),
        sa.Column("sample_size_a", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sample_size_b", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("concluded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ab_tests_tenant_prompt", "ab_tests", ["tenant_id", "prompt_name"])


def downgrade() -> None:
    op.drop_index("ix_ab_tests_tenant_prompt", table_name="ab_tests")
    op.drop_table("ab_tests")
    op.drop_index("ix_prompt_versions_tenant_name", table_name="prompt_versions")
    op.drop_table("prompt_versions")
