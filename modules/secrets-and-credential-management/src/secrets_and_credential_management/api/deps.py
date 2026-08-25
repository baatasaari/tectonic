from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, Request

from secrets_and_credential_management.app_context import AppContext
from secrets_and_credential_management.core.ports import SecretsRepository
from secrets_and_credential_management.core.rotation_service import RotationService
from secrets_and_credential_management.core.secret_access_service import SecretAccessService
from secrets_and_credential_management.core.secret_registry_service import SecretRegistryService
from secrets_and_credential_management.db.repository import SQLAlchemySecretsRepository


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


def resolve_tenant_id(request: Request, ctx: AppContext = Depends(get_ctx)) -> str:
    return request.headers.get("X-Tenant-Id", ctx.settings.tenant_id)


async def get_repository(ctx: AppContext = Depends(get_ctx)) -> AsyncIterator[SecretsRepository]:
    async with ctx.session_factory() as session:
        yield SQLAlchemySecretsRepository(session)


def build_secret_registry_service(repository: SecretsRepository, ctx: AppContext) -> SecretRegistryService:
    return SecretRegistryService(repository, ctx.cipher)


def build_secret_access_service(repository: SecretsRepository, ctx: AppContext) -> SecretAccessService:
    return SecretAccessService(repository, ctx.cipher, ctx.identity_access, ctx.auditability)


def build_rotation_service(repository: SecretsRepository, ctx: AppContext) -> RotationService:
    return RotationService(repository, ctx.cipher)
