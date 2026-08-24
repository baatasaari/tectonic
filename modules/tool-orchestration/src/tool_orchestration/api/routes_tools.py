"""`/v1/tool-orchestration/*` routes (LLD §3.3, §3.5)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from tool_orchestration.api.deps import (
    build_orchestration_service,
    build_synthesis_engine,
    get_ctx,
    get_repository,
)
from tool_orchestration.app_context import AppContext
from tool_orchestration.core.domain import (
    CircuitOpenError,
    SynthesisRejectedError,
    ToolCallError,
    ToolNotActiveError,
    ToolNotFoundError,
    ToolStatus,
)
from tool_orchestration.core.ports import ToolRepository
from tool_orchestration.schemas.tools import (
    ApproveToolRequest,
    ApproveToolResponse,
    InvokeToolRequest,
    InvokeToolResponse,
    ReliabilityScoreSummary,
    SynthesiseToolRequest,
    ToolDefinitionDetail,
    ToolDefinitionListResponse,
    ToolDefinitionSummary,
)

router = APIRouter(prefix="/v1/tool-orchestration", tags=["tools"])


def _tenant_id(request: Request, ctx: AppContext) -> str:
    return request.headers.get("X-Tenant-Id", ctx.settings.tenant_id)


@router.get("/tools", response_model=ToolDefinitionListResponse)
async def list_tools(
    request: Request,
    status: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ctx: AppContext = Depends(get_ctx),
    repository: ToolRepository = Depends(get_repository),
) -> ToolDefinitionListResponse:
    tools, total = await repository.list_tool_definitions(_tenant_id(request, ctx), status, limit=limit, offset=offset)
    return ToolDefinitionListResponse(
        items=[
            ToolDefinitionSummary(id=t.id, name=t.name, mcp_server_ref=t.mcp_server_ref, status=t.status.value, synthesised=t.synthesised)
            for t in tools
        ],
        total=total, limit=limit, offset=offset,
    )


@router.get("/tools/{tool_id}", response_model=ToolDefinitionDetail)
async def get_tool(
    tool_id: str,
    repository: ToolRepository = Depends(get_repository),
) -> ToolDefinitionDetail:
    tool = await repository.get_tool_definition(tool_id)
    if tool is None:
        raise HTTPException(status_code=404, detail="tool not found")
    score = await repository.get_reliability_score(tool_id)
    return ToolDefinitionDetail(
        id=tool.id, tenant_id=tool.tenant_id, name=tool.name, mcp_server_ref=tool.mcp_server_ref,
        schema_=tool.schema, status=tool.status.value, synthesised=tool.synthesised, created_at=tool.created_at,
        reliability_score=ReliabilityScoreSummary(
            rolling_success_rate=score.rolling_success_rate, rolling_avg_latency_ms=score.rolling_avg_latency_ms,
            last_updated_at=score.last_updated_at,
        ) if score else None,
    )


@router.post("/invoke", response_model=InvokeToolResponse)
async def invoke(
    body: InvokeToolRequest,
    request: Request,
    ctx: AppContext = Depends(get_ctx),
    repository: ToolRepository = Depends(get_repository),
) -> InvokeToolResponse:
    tenant_id = _tenant_id(request, ctx)
    service = await build_orchestration_service(ctx, repository, tenant_id)

    try:
        outcome = await service.invoke(
            tool_id=body.tool_id, arguments=body.parameters, agent_ref=body.agent_ref, tenant_id=tenant_id,
            workflow_instance_id=body.workflow_instance_id,
        )
    except ToolNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ToolNotActiveError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except CircuitOpenError as e:
        raise HTTPException(
            status_code=503,
            detail={"message": str(e), "suggestion": "circuit open — try an alternative tool for this capability"},
        ) from e
    except ToolCallError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    return InvokeToolResponse(
        result=outcome.output, status=outcome.status.value, retry_count=outcome.retry_count, latency_ms=outcome.latency_ms
    )


@router.post("/synthesise", response_model=ToolDefinitionSummary, status_code=201)
async def synthesise(
    body: SynthesiseToolRequest,
    request: Request,
    ctx: AppContext = Depends(get_ctx),
    repository: ToolRepository = Depends(get_repository),
) -> ToolDefinitionSummary:
    tenant_id = _tenant_id(request, ctx)
    engine = build_synthesis_engine(ctx, repository)
    try:
        tool = await engine.synthesise(
            gap_description=body.gap_description, available_primitives=body.available_primitives, tenant_id=tenant_id
        )
    except SynthesisRejectedError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    return ToolDefinitionSummary(id=tool.id, name=tool.name, mcp_server_ref=tool.mcp_server_ref, status=tool.status.value, synthesised=tool.synthesised)


@router.post("/tools/{tool_id}/approve", response_model=ApproveToolResponse)
async def approve_tool(
    tool_id: str,
    body: ApproveToolRequest,
    repository: ToolRepository = Depends(get_repository),
) -> ApproveToolResponse:
    tool = await repository.get_tool_definition(tool_id)
    if tool is None:
        raise HTTPException(status_code=404, detail="tool not found")
    if tool.status != ToolStatus.PENDING_REVIEW:
        raise HTTPException(status_code=409, detail=f"tool is not pending review (status={tool.status.value})")

    tool.status = ToolStatus.ACTIVE
    tool = await repository.update_tool_definition(tool)
    return ApproveToolResponse(status=tool.status.value)
