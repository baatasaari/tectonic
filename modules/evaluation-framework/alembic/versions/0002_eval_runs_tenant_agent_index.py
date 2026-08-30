"""index eval_runs (tenant_id, agent_ref) -- backs the new GET /eval-runs
lookup a release-gating caller (PromptOps' conclude, LLMOps' promote)
uses to find the eval_run_id its own /gate check should reference.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-31

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_eval_runs_tenant_agent", "eval_runs", ["tenant_id", "agent_ref"])


def downgrade() -> None:
    op.drop_index("ix_eval_runs_tenant_agent", table_name="eval_runs")
