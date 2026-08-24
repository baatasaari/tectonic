"""evidence_packs: durable job-queue columns for the SELECT FOR UPDATE
SKIP LOCKED worker (see core/evidence_worker.py) — replaces the previous
in-process FastAPI BackgroundTasks job, which lost in-flight generation
work on a pod restart.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-24

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("evidence_packs", sa.Column("worker_id", sa.String(64), nullable=True))
    op.add_column("evidence_packs", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "evidence_packs", sa.Column("attempts", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column("evidence_packs", sa.Column("last_error", sa.Text(), nullable=True))
    op.create_index(
        "ix_evidence_packs_status_lease", "evidence_packs", ["status", "lease_expires_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_evidence_packs_status_lease", table_name="evidence_packs")
    op.drop_column("evidence_packs", "last_error")
    op.drop_column("evidence_packs", "attempts")
    op.drop_column("evidence_packs", "lease_expires_at")
    op.drop_column("evidence_packs", "worker_id")
