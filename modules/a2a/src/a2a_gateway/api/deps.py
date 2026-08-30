from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, Request

from a2a_gateway.app_context import AppContext
from a2a_gateway.core.delegation_service import DelegationService
from a2a_gateway.core.ports import A2AGatewayRepository
from a2a_gateway.core.rpc_gateway import A2ARpcGateway
from a2a_gateway.db.repository import SQLAlchemyA2AGatewayRepository


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


def resolve_tenant_id(request: Request, ctx: AppContext = Depends(get_ctx)) -> str:
    return request.headers.get("X-Tenant-Id", ctx.settings.tenant_id)


def resolve_caller_agent_id(request: Request) -> str:
    """The `/v1/a2a/rpc` surface is deliberately excluded from this
    platform's shared-secret JWT (see security/jwt_auth.py) since an
    external caller was never issued that secret -- it self-declares its
    identity here instead, and the Access Policy Engine is what actually
    gates it: a caller id with no policy row for the target tenant gets
    zero access regardless of what it claims to be."""
    return request.headers.get("X-A2A-Caller-Id", "")


def resolve_caller_agent_url(request: Request) -> str:
    return request.headers.get("X-A2A-Caller-Url", "")


async def get_repository(ctx: AppContext = Depends(get_ctx)) -> AsyncIterator[A2AGatewayRepository]:
    async with ctx.session_factory() as session:
        yield SQLAlchemyA2AGatewayRepository(session)


def build_delegation_service(repository: A2AGatewayRepository, ctx: AppContext) -> DelegationService:
    return DelegationService(repository, ctx.peer_client, card_cache_ttl_seconds=ctx.settings.agent_card_cache_ttl_seconds)


def build_rpc_gateway(repository: A2AGatewayRepository, ctx: AppContext) -> A2ARpcGateway:
    return A2ARpcGateway(repository, ctx.workflow_client, ctx.settings.skill_definition_map)
