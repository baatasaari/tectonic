"""initial schema: workflow_definitions, workflow_instances, step_executions,
approval_requests, replan_events

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
        "workflow_definitions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("graph_schema", pg.JSONB(), nullable=False),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_workflow_definitions_tenant", "workflow_definitions", ["tenant_id"])
    op.create_index(
        "ix_workflow_definitions_name_version",
        "workflow_definitions",
        ["tenant_id", "name", "version"],
        unique=True,
    )

    op.create_table(
        "workflow_instances",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("definition_id", pg.UUID(as_uuid=True), sa.ForeignKey("workflow_definitions.id"), nullable=False),
        sa.Column("definition_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="running"),
        sa.Column("current_step_ids", pg.JSONB(), nullable=False, server_default="[]"),
        sa.Column("context", pg.JSONB(), nullable=False, server_default="{}"),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=False),
    )
    op.create_index("ix_workflow_instances_tenant", "workflow_instances", ["tenant_id"])
    op.create_index("ix_workflow_instances_status", "workflow_instances", ["tenant_id", "status"])

    op.create_table(
        "step_executions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("instance_id", pg.UUID(as_uuid=True), sa.ForeignKey("workflow_instances.id"), nullable=False),
        sa.Column("step_id", sa.String(255), nullable=False),
        sa.Column("execution_mode", sa.String(16), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("input_snapshot", pg.JSONB(), nullable=False, server_default="{}"),
        sa.Column("output", pg.JSONB(), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_step_executions_instance", "step_executions", ["instance_id"])

    op.create_table(
        "approval_requests",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("step_execution_id", pg.UUID(as_uuid=True), sa.ForeignKey("step_executions.id"), nullable=False),
        sa.Column("human_oversight_ref_id", sa.String(255), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "replan_events",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("instance_id", pg.UUID(as_uuid=True), sa.ForeignKey("workflow_instances.id"), nullable=False),
        sa.Column("trigger_reason", sa.String(255), nullable=False),
        sa.Column("original_step_id", sa.String(255), nullable=False),
        sa.Column("new_graph_delta", pg.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("replan_events")
    op.drop_table("approval_requests")
    op.drop_table("step_executions")
    op.drop_index("ix_workflow_instances_status", table_name="workflow_instances")
    op.drop_index("ix_workflow_instances_tenant", table_name="workflow_instances")
    op.drop_table("workflow_instances")
    op.drop_index("ix_workflow_definitions_name_version", table_name="workflow_definitions")
    op.drop_index("ix_workflow_definitions_tenant", table_name="workflow_definitions")
    op.drop_table("workflow_definitions")
