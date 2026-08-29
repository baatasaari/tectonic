"""OIDC/SAML federation + SCIM: identity_providers, groups, scim_tokens
tables, and new identities columns (email, external_provider_id,
external_subject, federated_role_names).

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-29

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("identities", sa.Column("email", sa.String(320), nullable=True))
    op.add_column("identities", sa.Column("external_provider_id", sa.String(255), nullable=True))
    op.add_column("identities", sa.Column("external_subject", sa.String(255), nullable=True))
    op.add_column(
        "identities",
        sa.Column("federated_role_names", pg.ARRAY(sa.String()), nullable=False, server_default="{}"),
    )
    op.create_index(
        "ix_identities_external_subject", "identities", ["tenant_id", "external_provider_id", "external_subject"],
    )

    op.create_table(
        "identity_providers",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("provider_type", sa.String(16), nullable=False),
        sa.Column("issuer", sa.String(500), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("client_id", sa.String(255), nullable=False, server_default=""),
        sa.Column("jwks_uri", sa.String(500), nullable=False, server_default=""),
        sa.Column("sso_url", sa.String(500), nullable=False, server_default=""),
        sa.Column("x509_certificate", sa.Text(), nullable=False, server_default=""),
        sa.Column("email_claim", sa.String(100), nullable=False, server_default="email"),
        sa.Column("groups_claim", sa.String(100), nullable=False, server_default="groups"),
        sa.Column("name_claim", sa.String(100), nullable=False, server_default="name"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            onupdate=sa.func.now(), nullable=False,
        ),
    )
    op.create_index("ix_identity_providers_tenant", "identity_providers", ["tenant_id"])

    op.create_table(
        "groups",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("provider_id", sa.String(255), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("default_role_names", pg.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("member_identity_ids", pg.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_groups_tenant_provider_external", "groups", ["tenant_id", "provider_id", "external_id"])

    op.create_table(
        "scim_tokens",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_scim_tokens_hash", "scim_tokens", ["token_hash"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_scim_tokens_hash", table_name="scim_tokens")
    op.drop_table("scim_tokens")
    op.drop_index("ix_groups_tenant_provider_external", table_name="groups")
    op.drop_table("groups")
    op.drop_index("ix_identity_providers_tenant", table_name="identity_providers")
    op.drop_table("identity_providers")
    op.drop_index("ix_identities_external_subject", table_name="identities")
    op.drop_column("identities", "federated_role_names")
    op.drop_column("identities", "external_subject")
    op.drop_column("identities", "external_provider_id")
    op.drop_column("identities", "email")
