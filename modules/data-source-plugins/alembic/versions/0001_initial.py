"""initial schema: connector_configs, schema_snapshots, sync_runs, quality_scores, drift_incidents

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
        "connector_configs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("connection_config", pg.JSONB(), nullable=False, server_default="{}"),
        sa.Column("secrets_ref", sa.String(255), nullable=False, server_default=""),
        sa.Column("sync_schedule", sa.String(64), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_connector_configs_tenant", "connector_configs", ["tenant_id"])

    op.create_table(
        "schema_snapshots",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("connector_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("schema", pg.JSONB(), nullable=False, server_default="{}"),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_schema_snapshots_connector", "schema_snapshots", ["connector_id", "version"])

    op.create_table(
        "sync_runs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("connector_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="running"),
        sa.Column("records_synced", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_sync_runs_connector", "sync_runs", ["connector_id"])

    op.create_table(
        "quality_scores",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("connector_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("sync_run_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("completeness_score", sa.Float(), nullable=False),
        sa.Column("freshness_score", sa.Float(), nullable=False),
        sa.Column("format_validity_score", sa.Float(), nullable=False),
        sa.Column("overall_score", sa.Float(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_quality_scores_connector", "quality_scores", ["connector_id"])

    op.create_table(
        "drift_incidents",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("connector_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("schema_diff", pg.JSONB(), nullable=False, server_default="{}"),
        sa.Column("classification", sa.String(32), nullable=False, server_default="additive"),
        sa.Column("auto_adapted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("resolved_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_drift_incidents_connector", "drift_incidents", ["connector_id"])


def downgrade() -> None:
    op.drop_index("ix_drift_incidents_connector", table_name="drift_incidents")
    op.drop_table("drift_incidents")
    op.drop_index("ix_quality_scores_connector", table_name="quality_scores")
    op.drop_table("quality_scores")
    op.drop_index("ix_sync_runs_connector", table_name="sync_runs")
    op.drop_table("sync_runs")
    op.drop_index("ix_schema_snapshots_connector", table_name="schema_snapshots")
    op.drop_table("schema_snapshots")
    op.drop_index("ix_connector_configs_tenant", table_name="connector_configs")
    op.drop_table("connector_configs")
