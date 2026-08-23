"""initial schema: eval_runs, metric_scores, gate_results, domain_metric_packs

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
        "eval_runs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("trigger_source", sa.String(32), nullable=False),
        sa.Column("agent_ref", sa.String(255), nullable=False),
        sa.Column("metrics_evaluated", pg.JSONB(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(24), nullable=False, server_default="running"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_eval_runs_tenant", "eval_runs", ["tenant_id"])

    op.create_table(
        "metric_scores",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("eval_run_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("agent_ref", sa.String(255), nullable=False),
        sa.Column("metric_name", sa.String(64), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_metric_scores_run", "metric_scores", ["eval_run_id"])
    op.create_index("ix_metric_scores_tenant_agent", "metric_scores", ["tenant_id", "agent_ref"])

    op.create_table(
        "gate_results",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("eval_run_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("overall_passed", sa.Boolean(), nullable=False),
        sa.Column("blocking_failures", pg.JSONB(), nullable=False, server_default="[]"),
        sa.Column("environment", sa.String(32), nullable=False, server_default="production"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_gate_results_run", "gate_results", ["eval_run_id"])

    op.create_table(
        "domain_metric_packs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("pack_name", sa.String(64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("custom_thresholds", pg.JSONB(), nullable=False, server_default="{}"),
    )
    op.create_index("ix_domain_metric_packs_tenant", "domain_metric_packs", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_domain_metric_packs_tenant", table_name="domain_metric_packs")
    op.drop_table("domain_metric_packs")
    op.drop_index("ix_gate_results_run", table_name="gate_results")
    op.drop_table("gate_results")
    op.drop_index("ix_metric_scores_tenant_agent", table_name="metric_scores")
    op.drop_index("ix_metric_scores_run", table_name="metric_scores")
    op.drop_table("metric_scores")
    op.drop_index("ix_eval_runs_tenant", table_name="eval_runs")
    op.drop_table("eval_runs")
