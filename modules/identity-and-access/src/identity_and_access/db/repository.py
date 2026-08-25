"""SQLAlchemy-backed implementation of IdentityAccessRepository (LLD §3)."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from identity_and_access.core.domain import (
    AuthDecisionRecord,
    IdentityRecord,
    IdentityStatus,
    IdentityType,
    RoleRecord,
)
from identity_and_access.db import models


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _identity_to_domain(m: models.Identity) -> IdentityRecord:
    return IdentityRecord(
        id=str(m.id), tenant_id=m.tenant_id, name=m.name, type=IdentityType(m.type), status=IdentityStatus(m.status),
        role_names=list(m.role_names or []), created_at=_as_utc(m.created_at), updated_at=_as_utc(m.updated_at),
    )


def _role_to_domain(m: models.Role) -> RoleRecord:
    return RoleRecord(name=m.name, scopes=list(m.scopes or []), description=m.description, created_at=_as_utc(m.created_at))


def _auth_decision_to_domain(m: models.AuthDecision) -> AuthDecisionRecord:
    return AuthDecisionRecord(
        id=str(m.id), tenant_id=m.tenant_id, identity_id=m.identity_id, required_scope=m.required_scope,
        allowed=m.allowed, reason=m.reason, checked_at=_as_utc(m.checked_at),
    )


class SQLAlchemyIdentityAccessRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_identity(self, record: IdentityRecord) -> IdentityRecord:
        m = models.Identity(
            id=record.id, tenant_id=record.tenant_id, name=record.name, type=record.type.value,
            status=record.status.value, role_names=record.role_names,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _identity_to_domain(m)

    async def get_identity(self, identity_id: str) -> IdentityRecord | None:
        m = await self.session.get(models.Identity, identity_id)
        return _identity_to_domain(m) if m else None

    async def update_identity(self, record: IdentityRecord) -> IdentityRecord:
        m = await self.session.get(models.Identity, record.id)
        m.status = record.status.value
        m.role_names = record.role_names
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
        m = models.Role(name=record.name, scopes=record.scopes, description=record.description)
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _role_to_domain(m)

    async def get_role(self, name: str) -> RoleRecord | None:
        m = await self.session.get(models.Role, name)
        return _role_to_domain(m) if m else None

    async def list_roles(self, *, limit: int = 50, offset: int = 0) -> tuple[list[RoleRecord], int]:
        count_stmt = select(func.count(models.Role.name))
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = select(models.Role).order_by(models.Role.created_at.desc()).limit(limit).offset(offset)
        rows = await self.session.execute(stmt)
        return [_role_to_domain(m) for m in rows.scalars().all()], total

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
