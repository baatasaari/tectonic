"""initial schema: retrieval_requests, retrieval_hops, retrieval_results

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
        "retrieval_requests",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("query", sa.String(), nullable=False),
        sa.Column("scope", pg.JSONB(), nullable=False, server_default="[]"),
        sa.Column("max_hops", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("groundedness_threshold", sa.Float(), nullable=False, server_default="0.85"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_retrieval_requests_tenant", "retrieval_requests", ["tenant_id"])

    op.create_table(
        "retrieval_hops",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_id", pg.UUID(as_uuid=True), sa.ForeignKey("retrieval_requests.id"), nullable=False),
        sa.Column("hop_number", sa.Integer(), nullable=False),
        sa.Column("reformulated_query", sa.String(), nullable=True),
        sa.Column("retrieved_items", pg.JSONB(), nullable=False, server_default="[]"),
        sa.Column("groundedness_score", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_retrieval_hops_request", "retrieval_hops", ["request_id"])

    op.create_table(
        "retrieval_results",
        sa.Column("request_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("final_context", sa.String(), nullable=False),
        sa.Column("total_hops", sa.Integer(), nullable=False),
        sa.Column("final_groundedness_score", sa.Float(), nullable=False),
        sa.Column("provenance_chain", pg.JSONB(), nullable=False, server_default="[]"),
        sa.Column("outcome", sa.String(32), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("retrieval_results")
    op.drop_index("ix_retrieval_hops_request", table_name="retrieval_hops")
    op.drop_table("retrieval_hops")
    op.drop_index("ix_retrieval_requests_tenant", table_name="retrieval_requests")
    op.drop_table("retrieval_requests")
