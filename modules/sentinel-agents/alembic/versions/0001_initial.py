"""initial schema: agent_baselines, alerts, intervention_records, swarm_correlation_windows

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
        "agent_baselines",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("agent_ref", sa.String(255), nullable=False),
        sa.Column("action_type", sa.String(128), nullable=False),
        sa.Column("mean", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("m2", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("sample_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "agent_ref", "action_type", name="uq_agent_baseline"),
    )

    op.create_table(
        "alerts",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("alert_type", sa.String(16), nullable=False),
        sa.Column("agent_refs", pg.JSONB(), nullable=False, server_default="[]"),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("description", sa.String(2048), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="detected"),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_alerts_tenant", "alerts", ["tenant_id"])

    op.create_table(
        "intervention_records",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("alert_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("intervention_type", sa.String(16), nullable=False),
        sa.Column("target_ref", sa.String(255), nullable=False, server_default=""),
        sa.Column("outcome", sa.String(64), nullable=False, server_default=""),
        sa.Column("executed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_intervention_records_alert", "intervention_records", ["alert_id"])

    op.create_table(
        "swarm_correlation_windows",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("agent_refs_involved", pg.JSONB(), nullable=False, server_default="[]"),
        sa.Column("correlation_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("pattern_description", sa.String(1024), nullable=False, server_default=""),
    )
    op.create_index("ix_swarm_windows_tenant", "swarm_correlation_windows", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_swarm_windows_tenant", table_name="swarm_correlation_windows")
    op.drop_table("swarm_correlation_windows")
    op.drop_index("ix_intervention_records_alert", table_name="intervention_records")
    op.drop_table("intervention_records")
    op.drop_index("ix_alerts_tenant", table_name="alerts")
    op.drop_table("alerts")
    op.drop_table("agent_baselines")
