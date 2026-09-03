"""`/v1/mcp/*` routes (LLD §3)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from mcp_gateway.api.deps import (
    build_capability_sync_service,
    build_registry_service,
    build_rpc_gateway,
    get_ctx,
    get_repository,
    resolve_tenant_id,
)
from mcp_gateway.app_context import AppContext
from mcp_gateway.core.domain import (
    AccessDeniedError,
    AccessPolicyRecord,
    JsonRpcRequest,
    McpServerNotFoundError,
    new_id,
)
from mcp_gateway.core.ports import MCPGatewayRepository
from mcp_gateway.schemas.mcp import (
    AccessPolicySchema,
    JsonRpcRequestSchema,
    JsonRpcResponseSchema,
    McpServerListResponse,
    McpServerSchema,
    McpToolSchema,
    RegisterServerRequest,
    SetAccessPolicyRequest,
)

router = APIRouter(prefix="/v1/mcp", tags=["mcp"])


def _reject_null_byte_query(**params: str | None) -> None:
    """A raw `Query()` string parameter never runs through a Pydantic
    body field's own NUL-byte validator -- a real CI run of a sibling
    module's contract tier (ticket #82) surfaced this exact bug class
    on a raw query parameter, an `UntranslatableCharacterError` at the
    database instead of a clean 422. Applied at the top of every route
    below taking a free-text (non-enum) query parameter."""
    for name, value in params.items():
        if value is not None and "\x00" in value:
            raise HTTPException(status_code=422, detail=f"{name} must not contain a NUL byte")


async def _server_schema(server, repository: MCPGatewayRepository) -> McpServerSchema:
    tools = await repository.list_tools(server.id)
    return McpServerSchema(
        id=server.id, tenant_id=server.tenant_id, name=server.name, description=server.description,
        base_url=server.base_url, status=server.status.value, created_at=server.created_at,
        tools=[McpToolSchema(name=t.name, description=t.description, input_schema=t.input_schema) for t in tools],
    )


@router.post("/servers", response_model=McpServerSchema, status_code=201)
async def register_server(
    body: RegisterServerRequest,
    tenant_id: str = Depends(resolve_tenant_id),
    repository: MCPGatewayRepository = Depends(get_repository),
) -> McpServerSchema:
    service = build_registry_service(repository)
    server = await service.register(tenant_id=tenant_id, name=body.name, description=body.description, base_url=body.base_url)
    return await _server_schema(server, repository)


@router.get("/servers", response_model=McpServerListResponse)
async def list_servers(
    tenant_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=1_000_000_000),
    repository: MCPGatewayRepository = Depends(get_repository),
) -> McpServerListResponse:
    _reject_null_byte_query(tenant_id=tenant_id)
    service = build_registry_service(repository)
    servers, total = await service.list(tenant_id=tenant_id, limit=limit, offset=offset)
    items = [await _server_schema(s, repository) for s in servers]
    return McpServerListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/servers/{server_id}", response_model=McpServerSchema)
async def get_server(
    server_id: str,
    repository: MCPGatewayRepository = Depends(get_repository),
) -> McpServerSchema:
    service = build_registry_service(repository)
    try:
        server = await service.get(server_id)
    except McpServerNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return await _server_schema(server, repository)


@router.post("/servers/{server_id}/sync", response_model=list[McpToolSchema])
async def sync_server(
    server_id: str,
    ctx: AppContext = Depends(get_ctx),
    repository: MCPGatewayRepository = Depends(get_repository),
) -> list[McpToolSchema]:
    service = build_capability_sync_service(repository, ctx)
    try:
        tools = await service.sync(server_id)
    except McpServerNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [McpToolSchema(name=t.name, description=t.description, input_schema=t.input_schema) for t in tools]


@router.put("/servers/{server_id}/access-policy", response_model=AccessPolicySchema)
async def set_access_policy(
    server_id: str,
    body: SetAccessPolicyRequest,
    tenant_id: str = Depends(resolve_tenant_id),
    repository: MCPGatewayRepository = Depends(get_repository),
) -> AccessPolicySchema:
    record = AccessPolicyRecord(id=new_id(), server_id=server_id, tenant_id=tenant_id, allowed_tools=body.allowed_tools)
    saved = await repository.upsert_access_policy(record)
    return AccessPolicySchema(server_id=saved.server_id, tenant_id=saved.tenant_id, allowed_tools=saved.allowed_tools)


@router.post("/servers/{server_id}/rpc", response_model=JsonRpcResponseSchema)
async def rpc(
    server_id: str,
    body: JsonRpcRequestSchema,
    ctx: AppContext = Depends(get_ctx),
    tenant_id: str = Depends(resolve_tenant_id),
    repository: MCPGatewayRepository = Depends(get_repository),
) -> JsonRpcResponseSchema:
    gateway = build_rpc_gateway(repository, ctx)
    jsonrpc_request = JsonRpcRequest(jsonrpc=body.jsonrpc, method=body.method, params=body.params, id=body.id)
    try:
        response = await gateway.handle(server_id=server_id, tenant_id=tenant_id, request=jsonrpc_request)
    except McpServerNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AccessDeniedError as exc:
        # Surfaced as a JSON-RPC error in the 200 body by RpcGateway itself in the normal
        # case; this except only covers a call site that bypasses that (defensive, not
        # expected to trigger given RpcGateway's own handling).
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return JsonRpcResponseSchema(jsonrpc=response.jsonrpc, id=response.id, result=response.result, error=response.error)
