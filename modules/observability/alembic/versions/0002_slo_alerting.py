"""trace query, SLO, and alerting surfaces: slos, alert_rules, alert_events

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-29

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
        "slos",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("metric", sa.String(32), nullable=False),
        sa.Column("target", sa.Float(), nullable=False),
        sa.Column("window_hours", sa.Integer(), nullable=False),
        sa.Column("service_name", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_slos_tenant", "slos", ["tenant_id"])

    op.create_table(
        "alert_rules",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("metric", sa.String(32), nullable=False),
        sa.Column("comparison", sa.String(8), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("window_hours", sa.Integer(), nullable=False),
        sa.Column("service_name", sa.String(64), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_alert_rules_tenant_enabled", "alert_rules", ["tenant_id", "enabled"])

    op.create_table(
        "alert_events",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("rule_id", sa.String(255), nullable=False),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_alert_events_rule", "alert_events", ["rule_id"])
    op.create_index("ix_alert_events_tenant_status", "alert_events", ["tenant_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_alert_events_tenant_status", table_name="alert_events")
    op.drop_index("ix_alert_events_rule", table_name="alert_events")
    op.drop_table("alert_events")
    op.drop_index("ix_alert_rules_tenant_enabled", table_name="alert_rules")
    op.drop_table("alert_rules")
    op.drop_index("ix_slos_tenant", table_name="slos")
    op.drop_table("slos")
