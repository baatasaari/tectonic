from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request

from data_source_plugins.app_context import AppContext
from data_source_plugins.core.ports import ConnectorRepository
from data_source_plugins.core.sync_service import SyncService
from data_source_plugins.db.repository import SQLAlchemyConnectorRepository


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


async def get_repository(request: Request) -> AsyncIterator[ConnectorRepository]:
    ctx: AppContext = request.app.state.ctx
    async with ctx.session_factory() as session:
        yield SQLAlchemyConnectorRepository(session)


def build_sync_service(ctx: AppContext, repository: ConnectorRepository) -> SyncService:
    return SyncService(
        repository, ctx.connector_runtime, ctx.secrets_client, ctx.settings.drift, ctx.settings.quality,
    )
