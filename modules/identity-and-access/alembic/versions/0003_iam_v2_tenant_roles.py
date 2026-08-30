"""IAM v2 foundation: tenant-scoped roles (roles.name was the sole,
platform-global primary key before -- see core/domain.py's
PLATFORM_TENANT_ID docstring for the full reasoning) and a new
role_bindings table, the durable grant/revoke audit trail
RoleBindingService writes to.

Every existing role predates tenant scoping -- under the old model it
was implicitly usable by every tenant, so it's backfilled as a
platform-wide role (tenant_id = PLATFORM_TENANT_ID) rather than
arbitrarily assigned to one tenant, preserving exactly the access every
existing identity already had.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-30

"""
from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

PLATFORM_TENANT_ID = "__platform__"


def upgrade() -> None:
    op.add_column("roles", sa.Column("id", pg.UUID(as_uuid=True), nullable=True))
    op.add_column("roles", sa.Column("tenant_id", sa.String(255), nullable=True))

    # Backfill in Python, not a DB-side UUID-generation function -- this
    # platform doesn't otherwise depend on pgcrypto/uuid-ossp, and every
    # other module-31 id is app-generated the same way (core/domain.py's
    # new_id()); no reason for this one migration to be the first to need
    # a new Postgres extension.
    bind = op.get_bind()
    roles_table = sa.table("roles", sa.column("name", sa.String), sa.column("id", pg.UUID), sa.column("tenant_id", sa.String))
    existing_names = bind.execute(sa.select(roles_table.c.name)).scalars().all()
    for name in existing_names:
        bind.execute(
            roles_table.update()
            .where(roles_table.c.name == name)
            .values(id=str(uuid.uuid4()), tenant_id=PLATFORM_TENANT_ID),
        )

    op.alter_column("roles", "id", nullable=False)
    op.alter_column("roles", "tenant_id", nullable=False)

    op.drop_constraint("roles_pkey", "roles", type_="primary")
    op.create_primary_key("roles_pkey", "roles", ["id"])
    op.create_unique_constraint("uq_roles_tenant_name", "roles", ["tenant_id", "name"])

    op.create_table(
        "role_bindings",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("identity_id", sa.String(255), nullable=False),
        sa.Column("role_name", sa.String(255), nullable=False),
        sa.Column("granted_by", sa.String(255), nullable=False, server_default=""),
        sa.Column("granted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_role_bindings_identity_role", "role_bindings", ["identity_id", "role_name"])
    op.create_index("ix_role_bindings_tenant", "role_bindings", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_role_bindings_tenant", table_name="role_bindings")
    op.drop_index("ix_role_bindings_identity_role", table_name="role_bindings")
    op.drop_table("role_bindings")

    op.drop_constraint("uq_roles_tenant_name", "roles", type_="unique")
    op.drop_constraint("roles_pkey", "roles", type_="primary")
    op.create_primary_key("roles_pkey", "roles", ["name"])
    op.drop_column("roles", "tenant_id")
    op.drop_column("roles", "id")
