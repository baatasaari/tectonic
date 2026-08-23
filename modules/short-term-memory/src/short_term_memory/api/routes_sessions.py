"""`/v1/short-term-memory/*` routes (LLD §3)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from short_term_memory.api.deps import get_ctx
from short_term_memory.app_context import AppContext
from short_term_memory.schemas.messages import (
    AppendMessageRequest,
    AppendResponse,
    BufferStateSchema,
    DeleteResponse,
    MessageSchema,
)

router = APIRouter(prefix="/v1/short-term-memory", tags=["short-term-memory"])


def _tenant_id(request: Request, ctx: AppContext) -> str:
    return request.headers.get("X-Tenant-Id", ctx.settings.tenant_id)


@router.post("/sessions/{session_id}/messages", response_model=AppendResponse)
async def append_message(
    session_id: str,
    body: AppendMessageRequest,
    request: Request,
    ctx: AppContext = Depends(get_ctx),
) -> AppendResponse:
    result = await ctx.buffer_manager.append(session_id, _tenant_id(request, ctx), body.content, body.role)
    return AppendResponse(token_count=result.state.token_count, overflow_triggered=result.overflow_triggered)


@router.get("/sessions/{session_id}", response_model=BufferStateSchema)
async def get_session(
    session_id: str,
    ctx: AppContext = Depends(get_ctx),
) -> BufferStateSchema:
    state = await ctx.buffer_manager.get(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="session not found")
    return BufferStateSchema(
        session_id=state.session_id,
        messages=[
            MessageSchema(content=m.content, role=m.role, token_count=m.token_count, salience_score=m.salience_score, timestamp=m.timestamp)
            for m in state.messages
        ],
        summary=state.summary,
        token_count=state.token_count,
    )


@router.delete("/sessions/{session_id}", response_model=DeleteResponse)
async def delete_session(
    session_id: str,
    ctx: AppContext = Depends(get_ctx),
) -> DeleteResponse:
    existed = await ctx.buffer_manager.delete(session_id)
    return DeleteResponse(status="deleted" if existed else "not_found")
