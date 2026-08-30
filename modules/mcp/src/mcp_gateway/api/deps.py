from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, Request

from mcp_gateway.app_context import AppContext
from mcp_gateway.core.capability_sync_service import CapabilitySyncService
from mcp_gateway.core.ports import MCPGatewayRepository
from mcp_gateway.core.registry_service import RegistryService
from mcp_gateway.core.rpc_gateway import RpcGateway
from mcp_gateway.db.repository import SQLAlchemyMCPGatewayRepository


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


def resolve_tenant_id(request: Request, ctx: AppContext = Depends(get_ctx)) -> str:
    return request.headers.get("X-Tenant-Id", ctx.settings.tenant_id)


async def get_repository(ctx: AppContext = Depends(get_ctx)) -> AsyncIterator[MCPGatewayRepository]:
    async with ctx.session_factory() as session:
        yield SQLAlchemyMCPGatewayRepository(session)


def build_registry_service(repository: MCPGatewayRepository) -> RegistryService:
    return RegistryService(repository)


def build_rpc_gateway(repository: MCPGatewayRepository, ctx: AppContext) -> RpcGateway:
    return RpcGateway(repository, ctx.backend)


def build_capability_sync_service(repository: MCPGatewayRepository, ctx: AppContext) -> CapabilitySyncService:
    return CapabilitySyncService(repository, ctx.backend)
