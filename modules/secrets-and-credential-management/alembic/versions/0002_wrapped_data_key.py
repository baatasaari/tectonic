"""real envelope encryption: secret_versions.wrapped_data_key

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-29

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
    # server_default="" only to satisfy NOT NULL for any pre-existing row (this
    # platform's own sandbox/dev data, never real production secrets) -- every row
    # written from here on always supplies a real wrapped_data_key explicitly; see
    # security/envelope_encryption.py and security/key_management.py.
    op.add_column(
        "secret_versions", sa.Column("wrapped_data_key", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("secret_versions", "wrapped_data_key")
