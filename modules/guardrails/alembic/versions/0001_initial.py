"""initial schema: policy_profiles, intervention_logs, red_team_runs, bypass_incidents

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
        "policy_profiles",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("enabled_checks", pg.JSONB(), nullable=False, server_default="[]"),
        sa.Column("pii_entity_types", pg.JSONB(), nullable=False, server_default="[]"),
        sa.Column("denied_topics", pg.JSONB(), nullable=False, server_default="[]"),
        sa.Column("groundedness_threshold", sa.Float(), nullable=False, server_default="0.85"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_policy_profiles_tenant", "policy_profiles", ["tenant_id"])

    op.create_table(
        "intervention_logs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("policy_profile_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("stage", sa.String(16), nullable=False),
        sa.Column("check_type", sa.String(64), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("violation_category", sa.String(64), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_intervention_logs_tenant", "intervention_logs", ["tenant_id"])

    op.create_table(
        "red_team_runs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("attempts_generated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("successful_bypasses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("run_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_red_team_runs_tenant", "red_team_runs", ["tenant_id"])

    op.create_table(
        "bypass_incidents",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("red_team_run_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("attack_pattern", sa.String(1024), nullable=False),
        sa.Column("target_check", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False, server_default="high"),
        sa.Column("resolved", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.create_index("ix_bypass_incidents_run", "bypass_incidents", ["red_team_run_id"])


def downgrade() -> None:
    op.drop_index("ix_bypass_incidents_run", table_name="bypass_incidents")
    op.drop_table("bypass_incidents")
    op.drop_index("ix_red_team_runs_tenant", table_name="red_team_runs")
    op.drop_table("red_team_runs")
    op.drop_index("ix_intervention_logs_tenant", table_name="intervention_logs")
    op.drop_table("intervention_logs")
    op.drop_index("ix_policy_profiles_tenant", table_name="policy_profiles")
    op.drop_table("policy_profiles")
