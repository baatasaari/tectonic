"""SQLAlchemy-backed implementation of IdentityAccessRepository (LLD §3,
extended for OIDC/SAML federation + SCIM)."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from identity_and_access.core.domain import (
    PLATFORM_TENANT_ID,
    AuthDecisionRecord,
    GroupRecord,
    IdentityProviderRecord,
    IdentityProviderType,
    IdentityRecord,
    IdentityStatus,
    IdentityType,
    RoleBindingRecord,
    RoleRecord,
    ScimTokenRecord,
)
from identity_and_access.db import models


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _identity_to_domain(m: models.Identity) -> IdentityRecord:
    return IdentityRecord(
        id=str(m.id), tenant_id=m.tenant_id, name=m.name, type=IdentityType(m.type), status=IdentityStatus(m.status),
        role_names=list(m.role_names or []), email=m.email, external_provider_id=m.external_provider_id,
        external_subject=m.external_subject, federated_role_names=list(m.federated_role_names or []),
        created_at=_as_utc(m.created_at), updated_at=_as_utc(m.updated_at),
    )


def _role_to_domain(m: models.Role) -> RoleRecord:
    return RoleRecord(
        id=str(m.id), tenant_id=m.tenant_id, name=m.name, scopes=list(m.scopes or []),
        description=m.description, created_at=_as_utc(m.created_at),
    )


def _role_binding_to_domain(m: models.RoleBinding) -> RoleBindingRecord:
    return RoleBindingRecord(
        id=str(m.id), tenant_id=m.tenant_id, identity_id=m.identity_id, role_name=m.role_name,
        granted_by=m.granted_by, granted_at=_as_utc(m.granted_at), revoked_at=_as_utc(m.revoked_at),
    )


def _auth_decision_to_domain(m: models.AuthDecision) -> AuthDecisionRecord:
    return AuthDecisionRecord(
        id=str(m.id), tenant_id=m.tenant_id, identity_id=m.identity_id, required_scope=m.required_scope,
        allowed=m.allowed, reason=m.reason, checked_at=_as_utc(m.checked_at),
    )


def _provider_to_domain(m: models.IdentityProvider) -> IdentityProviderRecord:
    return IdentityProviderRecord(
        id=str(m.id), tenant_id=m.tenant_id, name=m.name, provider_type=IdentityProviderType(m.provider_type),
        issuer=m.issuer, enabled=m.enabled, client_id=m.client_id, jwks_uri=m.jwks_uri, sso_url=m.sso_url,
        x509_certificate=m.x509_certificate, email_claim=m.email_claim, groups_claim=m.groups_claim,
        name_claim=m.name_claim, created_at=_as_utc(m.created_at), updated_at=_as_utc(m.updated_at),
    )


def _group_to_domain(m: models.Group) -> GroupRecord:
    return GroupRecord(
        id=str(m.id), tenant_id=m.tenant_id, provider_id=m.provider_id, external_id=m.external_id, name=m.name,
        default_role_names=list(m.default_role_names or []), member_identity_ids=list(m.member_identity_ids or []),
        created_at=_as_utc(m.created_at),
    )


def _scim_token_to_domain(m: models.ScimToken) -> ScimTokenRecord:
    return ScimTokenRecord(
        id=str(m.id), tenant_id=m.tenant_id, name=m.name, token_hash=m.token_hash, revoked=m.revoked,
        created_at=_as_utc(m.created_at),
    )


class SQLAlchemyIdentityAccessRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_identity(self, record: IdentityRecord) -> IdentityRecord:
        m = models.Identity(
            id=record.id, tenant_id=record.tenant_id, name=record.name, type=record.type.value,
            status=record.status.value, role_names=record.role_names, email=record.email,
            external_provider_id=record.external_provider_id, external_subject=record.external_subject,
            federated_role_names=record.federated_role_names,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _identity_to_domain(m)

    async def get_identity(self, identity_id: str) -> IdentityRecord | None:
        m = await self.session.get(models.Identity, identity_id)
        return _identity_to_domain(m) if m else None

    async def find_identity_by_external_subject(
        self, *, tenant_id: str, provider_id: str, external_subject: str,
    ) -> IdentityRecord | None:
        stmt = select(models.Identity).where(
            models.Identity.tenant_id == tenant_id,
            models.Identity.external_provider_id == provider_id,
            models.Identity.external_subject == external_subject,
        )
        m = (await self.session.execute(stmt)).scalars().first()
        return _identity_to_domain(m) if m else None

    async def update_identity(self, record: IdentityRecord) -> IdentityRecord:
        m = await self.session.get(models.Identity, record.id)
        m.status = record.status.value
        m.role_names = record.role_names
        m.email = record.email
        m.external_provider_id = record.external_provider_id
        m.external_subject = record.external_subject
        m.federated_role_names = record.federated_role_names
        await self.session.commit()
        await self.session.refresh(m)
        return _identity_to_domain(m)

    async def list_identities(
        self, *, tenant_id: str | None = None, status: IdentityStatus | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[IdentityRecord], int]:
        filters = []
        if tenant_id is not None:
            filters.append(models.Identity.tenant_id == tenant_id)
        if status is not None:
            filters.append(models.Identity.status == status.value)

        count_stmt = select(func.count(models.Identity.id)).where(*filters)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = select(models.Identity).where(*filters).order_by(models.Identity.created_at.desc()).limit(limit).offset(offset)
        rows = await self.session.execute(stmt)
        return [_identity_to_domain(m) for m in rows.scalars().all()], total

    async def create_role(self, record: RoleRecord) -> RoleRecord:
        m = models.Role(
            id=record.id, tenant_id=record.tenant_id, name=record.name,
            scopes=record.scopes, description=record.description,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _role_to_domain(m)

    async def get_role_by_tenant_and_name(self, tenant_id: str, name: str) -> RoleRecord | None:
        stmt = select(models.Role).where(models.Role.tenant_id == tenant_id, models.Role.name == name)
        m = (await self.session.execute(stmt)).scalars().first()
        return _role_to_domain(m) if m else None

    async def get_role(self, tenant_id: str, name: str) -> RoleRecord | None:
        role = await self.get_role_by_tenant_and_name(tenant_id, name)
        if role is not None:
            return role
        if tenant_id == PLATFORM_TENANT_ID:
            return None
        return await self.get_role_by_tenant_and_name(PLATFORM_TENANT_ID, name)

    async def list_roles(
        self, *, tenant_id: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[RoleRecord], int]:
        filters = []
        if tenant_id is not None:
            filters.append(models.Role.tenant_id == tenant_id)

        count_stmt = select(func.count(models.Role.id)).where(*filters)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = select(models.Role).where(*filters).order_by(models.Role.created_at.desc()).limit(limit).offset(offset)
        rows = await self.session.execute(stmt)
        return [_role_to_domain(m) for m in rows.scalars().all()], total

    async def create_role_binding(self, record: RoleBindingRecord) -> RoleBindingRecord:
        m = models.RoleBinding(
            id=record.id, tenant_id=record.tenant_id, identity_id=record.identity_id,
            role_name=record.role_name, granted_by=record.granted_by,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _role_binding_to_domain(m)

    async def get_active_role_binding(self, *, identity_id: str, role_name: str) -> RoleBindingRecord | None:
        stmt = (
            select(models.RoleBinding)
            .where(
                models.RoleBinding.identity_id == identity_id,
                models.RoleBinding.role_name == role_name,
                models.RoleBinding.revoked_at.is_(None),
            )
            .order_by(models.RoleBinding.granted_at.desc())
        )
        m = (await self.session.execute(stmt)).scalars().first()
        return _role_binding_to_domain(m) if m else None

    async def revoke_role_binding(self, binding_id: str) -> RoleBindingRecord | None:
        m = await self.session.get(models.RoleBinding, binding_id)
        if m is None:
            return None
        m.revoked_at = datetime.now(UTC)
        await self.session.commit()
        await self.session.refresh(m)
        return _role_binding_to_domain(m)

    async def list_role_bindings(
        self, *, tenant_id: str | None = None, identity_id: str | None = None, role_name: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[RoleBindingRecord], int]:
        filters = []
        if tenant_id is not None:
            filters.append(models.RoleBinding.tenant_id == tenant_id)
        if identity_id is not None:
            filters.append(models.RoleBinding.identity_id == identity_id)
        if role_name is not None:
            filters.append(models.RoleBinding.role_name == role_name)

        count_stmt = select(func.count(models.RoleBinding.id)).where(*filters)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            select(models.RoleBinding).where(*filters).order_by(models.RoleBinding.granted_at.desc())
            .limit(limit).offset(offset)
        )
        rows = await self.session.execute(stmt)
        return [_role_binding_to_domain(m) for m in rows.scalars().all()], total

    async def create_auth_decision(self, record: AuthDecisionRecord) -> AuthDecisionRecord:
        m = models.AuthDecision(
            id=record.id, tenant_id=record.tenant_id, identity_id=record.identity_id,
            required_scope=record.required_scope, allowed=record.allowed, reason=record.reason,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _auth_decision_to_domain(m)

    async def list_auth_decisions(
        self, *, identity_id: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[AuthDecisionRecord], int]:
        filters = []
        if identity_id is not None:
            filters.append(models.AuthDecision.identity_id == identity_id)

        count_stmt = select(func.count(models.AuthDecision.id)).where(*filters)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            select(models.AuthDecision).where(*filters).order_by(models.AuthDecision.checked_at.desc())
            .limit(limit).offset(offset)
        )
        rows = await self.session.execute(stmt)
        return [_auth_decision_to_domain(m) for m in rows.scalars().all()], total

    async def create_identity_provider(self, record: IdentityProviderRecord) -> IdentityProviderRecord:
        m = models.IdentityProvider(
            id=record.id, tenant_id=record.tenant_id, name=record.name, provider_type=record.provider_type.value,
            issuer=record.issuer, enabled=record.enabled, client_id=record.client_id, jwks_uri=record.jwks_uri,
            sso_url=record.sso_url, x509_certificate=record.x509_certificate, email_claim=record.email_claim,
            groups_claim=record.groups_claim, name_claim=record.name_claim,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _provider_to_domain(m)

    async def get_identity_provider(self, provider_id: str) -> IdentityProviderRecord | None:
        m = await self.session.get(models.IdentityProvider, provider_id)
        return _provider_to_domain(m) if m else None

    async def list_identity_providers(
        self, *, tenant_id: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[IdentityProviderRecord], int]:
        filters = []
        if tenant_id is not None:
            filters.append(models.IdentityProvider.tenant_id == tenant_id)

        count_stmt = select(func.count(models.IdentityProvider.id)).where(*filters)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            select(models.IdentityProvider).where(*filters).order_by(models.IdentityProvider.created_at.desc())
            .limit(limit).offset(offset)
        )
        rows = await self.session.execute(stmt)
        return [_provider_to_domain(m) for m in rows.scalars().all()], total

    async def update_identity_provider(self, record: IdentityProviderRecord) -> IdentityProviderRecord:
        m = await self.session.get(models.IdentityProvider, record.id)
        m.name = record.name
        m.issuer = record.issuer
        m.enabled = record.enabled
        m.client_id = record.client_id
        m.jwks_uri = record.jwks_uri
        m.sso_url = record.sso_url
        m.x509_certificate = record.x509_certificate
        m.email_claim = record.email_claim
        m.groups_claim = record.groups_claim
        m.name_claim = record.name_claim
        await self.session.commit()
        await self.session.refresh(m)
        return _provider_to_domain(m)

    async def create_group(self, record: GroupRecord) -> GroupRecord:
        m = models.Group(
            id=record.id, tenant_id=record.tenant_id, provider_id=record.provider_id, external_id=record.external_id,
            name=record.name, default_role_names=record.default_role_names,
            member_identity_ids=record.member_identity_ids,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _group_to_domain(m)

    async def get_group(self, group_id: str) -> GroupRecord | None:
        m = await self.session.get(models.Group, group_id)
        return _group_to_domain(m) if m else None

    async def find_group_by_external_id(
        self, *, tenant_id: str, provider_id: str, external_id: str,
    ) -> GroupRecord | None:
        stmt = select(models.Group).where(
            models.Group.tenant_id == tenant_id,
            models.Group.provider_id == provider_id,
            models.Group.external_id == external_id,
        )
        m = (await self.session.execute(stmt)).scalars().first()
        return _group_to_domain(m) if m else None

    async def list_groups(
        self, *, tenant_id: str | None = None, provider_id: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[GroupRecord], int]:
        filters = []
        if tenant_id is not None:
            filters.append(models.Group.tenant_id == tenant_id)
        if provider_id is not None:
            filters.append(models.Group.provider_id == provider_id)

        count_stmt = select(func.count(models.Group.id)).where(*filters)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = select(models.Group).where(*filters).order_by(models.Group.created_at.desc()).limit(limit).offset(offset)
        rows = await self.session.execute(stmt)
        return [_group_to_domain(m) for m in rows.scalars().all()], total

    async def update_group(self, record: GroupRecord) -> GroupRecord:
        m = await self.session.get(models.Group, record.id)
        m.name = record.name
        m.default_role_names = record.default_role_names
        m.member_identity_ids = record.member_identity_ids
        await self.session.commit()
        await self.session.refresh(m)
        return _group_to_domain(m)

    async def create_scim_token(self, record: ScimTokenRecord) -> ScimTokenRecord:
        m = models.ScimToken(
            id=record.id, tenant_id=record.tenant_id, name=record.name, token_hash=record.token_hash,
            revoked=record.revoked,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _scim_token_to_domain(m)

    async def get_scim_token_by_hash(self, token_hash: str) -> ScimTokenRecord | None:
        stmt = select(models.ScimToken).where(models.ScimToken.token_hash == token_hash)
        m = (await self.session.execute(stmt)).scalars().first()
        return _scim_token_to_domain(m) if m else None

    async def list_scim_tokens(
        self, *, tenant_id: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[ScimTokenRecord], int]:
        filters = []
        if tenant_id is not None:
            filters.append(models.ScimToken.tenant_id == tenant_id)

        count_stmt = select(func.count(models.ScimToken.id)).where(*filters)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            select(models.ScimToken).where(*filters).order_by(models.ScimToken.created_at.desc())
            .limit(limit).offset(offset)
        )
        rows = await self.session.execute(stmt)
        return [_scim_token_to_domain(m) for m in rows.scalars().all()], total

    async def revoke_scim_token(self, token_id: str) -> ScimTokenRecord | None:
        m = await self.session.get(models.ScimToken, token_id)
        if m is None:
            return None
        m.revoked = True
        await self.session.commit()
        await self.session.refresh(m)
        return _scim_token_to_domain(m)
