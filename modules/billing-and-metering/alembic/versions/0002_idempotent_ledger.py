"""idempotent metering ledger: unique (tenant_id, period, resource) on
usage_records, unique (tenant_id, period) on invoices

Both constraints assume no pre-existing duplicate rows -- true for this
platform's own dev/test data. A production deployment carrying real
duplicates from before this fix would need a one-time dedup pass
(keep the newest row per key) before this migration could apply; that
dedup is real, separate, environment-specific work this migration
deliberately doesn't fabricate a generic answer for.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-29

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_usage_records_tenant_period_resource", "usage_records", ["tenant_id", "period", "resource"],
    )
    op.create_unique_constraint("uq_invoices_tenant_period", "invoices", ["tenant_id", "period"])


def downgrade() -> None:
    op.drop_constraint("uq_invoices_tenant_period", "invoices", type_="unique")
    op.drop_constraint("uq_usage_records_tenant_period_resource", "usage_records", type_="unique")
