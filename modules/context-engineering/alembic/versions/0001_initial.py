"""initial schema: ontology_configs, prioritisation_weights, context_assemblies

Revision ID: 0001
Revises:
Create Date: 2026-08-23

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
        "ontology_configs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("roles", pg.JSONB(), nullable=False, server_default="[]"),
        sa.Column("entity_types", pg.JSONB(), nullable=False, server_default="[]"),
        sa.Column("policy_tags", pg.JSONB(), nullable=False, server_default="[]"),
    )
    op.create_index("ix_ontology_configs_tenant_version", "ontology_configs", ["tenant_id", "version"], unique=True)

    op.create_table(
        "prioritisation_weights",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("task_type", sa.String(255), nullable=False),
        sa.Column("feature_weights", pg.JSONB(), nullable=False, server_default="{}"),
        sa.Column("last_updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_prioritisation_weights_tenant_task", "prioritisation_weights", ["tenant_id", "task_type"], unique=True
    )

    op.create_table(
        "context_assemblies",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_ref", sa.String(255), nullable=False),
        sa.Column("task_type", sa.String(255), nullable=False),
        sa.Column("items_included", pg.JSONB(), nullable=False, server_default="[]"),
        sa.Column("items_dropped", pg.JSONB(), nullable=False, server_default="[]"),
        sa.Column("items_summarised", pg.JSONB(), nullable=False, server_default="[]"),
        sa.Column("total_tokens_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_context_assemblies_request_ref", "context_assemblies", ["request_ref"])


def downgrade() -> None:
    op.drop_index("ix_context_assemblies_request_ref", table_name="context_assemblies")
    op.drop_table("context_assemblies")
    op.drop_index("ix_prioritisation_weights_tenant_task", table_name="prioritisation_weights")
    op.drop_table("prioritisation_weights")
    op.drop_index("ix_ontology_configs_tenant_version", table_name="ontology_configs")
    op.drop_table("ontology_configs")
