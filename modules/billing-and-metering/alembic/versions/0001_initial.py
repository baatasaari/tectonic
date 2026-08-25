"""initial schema: pricing_plans, usage_records, invoices, invoice_lines

Revision ID: 0001
Revises:
Create Date: 2026-08-25

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
        "pricing_plans",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("unit_prices", pg.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_pricing_plans_tenant", "pricing_plans", ["tenant_id"])

    op.create_table(
        "usage_records",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("period", sa.String(16), nullable=False),
        sa.Column("resource", sa.String(255), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_usage_records_tenant_period", "usage_records", ["tenant_id", "period"])

    op.create_table(
        "invoices",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("period", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("total_amount", sa.Float(), nullable=False, server_default="0"),
        sa.Column("complete", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_invoices_tenant_status", "invoices", ["tenant_id", "status"])

    op.create_table(
        "invoice_lines",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("invoice_id", sa.String(255), nullable=False),
        sa.Column("resource", sa.String(255), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("unit_price", sa.Float(), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
    )
    op.create_index("ix_invoice_lines_invoice", "invoice_lines", ["invoice_id"])


def downgrade() -> None:
    op.drop_index("ix_invoice_lines_invoice", table_name="invoice_lines")
    op.drop_table("invoice_lines")
    op.drop_index("ix_invoices_tenant_status", table_name="invoices")
    op.drop_table("invoices")
    op.drop_index("ix_usage_records_tenant_period", table_name="usage_records")
    op.drop_table("usage_records")
    op.drop_index("ix_pricing_plans_tenant", table_name="pricing_plans")
    op.drop_table("pricing_plans")
