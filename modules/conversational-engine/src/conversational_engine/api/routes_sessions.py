"""`/v1/conversational-engine/sessions` routes (LLD §3.3, §3.4)."""
from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sse_starlette.sse import EventSourceResponse

from conversational_engine.api.deps import build_session_manager, get_ctx, get_repository
from conversational_engine.app_context import AppContext
from conversational_engine.core.domain import Channel, SessionStatus, now
from conversational_engine.core.ports import ConversationRepository
from conversational_engine.schemas.sessions import (
    CreateSessionRequest,
    CreateSessionResponse,
    HandoffRequest,
    HandoffResponse,
    MessageSummary,
    SendMessageRequest,
    SessionDetail,
    StatusResponse,
    TurnResponse,
)

router = APIRouter(prefix="/v1/conversational-engine/sessions", tags=["sessions"])


def _tenant_id(request: Request, ctx: AppContext) -> str:
    return request.headers.get("X-Tenant-Id", ctx.settings.tenant_id)


def _message_summary(m) -> MessageSummary:
    return MessageSummary(
        id=m.id, direction=m.direction.value, content=m.content, emotion_score=m.emotion_score, created_at=m.created_at
    )


@router.post("", response_model=CreateSessionResponse, status_code=201)
async def create_session(
    body: CreateSessionRequest,
    request: Request,
    ctx: AppContext = Depends(get_ctx),
    repository: ConversationRepository = Depends(get_repository),
) -> CreateSessionResponse:
    try:
        channel = Channel(body.channel)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"unknown channel '{body.channel}'") from e

    manager = build_session_manager(ctx, repository)
    session = await manager.create_session(
        tenant_id=_tenant_id(request, ctx),
        channel=channel,
        persona_config_ref=body.persona_config_ref,
        trace_id=uuid.uuid4().hex,
        user_ref=body.user_ref,
    )
    return CreateSessionResponse(id=session.id, status=session.status.value)


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session(
    session_id: str,
    repository: ConversationRepository = Depends(get_repository),
) -> SessionDetail:
    session = await repository.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    messages = await repository.list_messages(session_id)
    return SessionDetail(
        id=session.id,
        tenant_id=session.tenant_id,
        channel=session.channel.value,
        status=session.status.value,
        persona_config_ref=session.persona_config_ref,
        trace_id=session.trace_id,
        created_at=session.created_at,
        last_activity_at=session.last_activity_at,
        messages=[_message_summary(m) for m in messages],
    )


@router.post("/{session_id}/messages")
async def send_message(
    session_id: str,
    body: SendMessageRequest,
    request: Request,
    stream: bool = Query(False, description="If true, respond as an SSE token stream instead of a single JSON body"),
    ctx: AppContext = Depends(get_ctx),
    repository: ConversationRepository = Depends(get_repository),
):
    session = await repository.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    if session.status not in (SessionStatus.ACTIVE, SessionStatus.PAUSED):
        raise HTTPException(status_code=409, detail=f"cannot send a message to a session in status {session.status.value}")

    manager = build_session_manager(ctx, repository)
    wants_stream = stream or "text/event-stream" in request.headers.get("accept", "")

    if not wants_stream:
        result = await manager.handle_turn(session, body.content)
        return TurnResponse(
            outbound_message=_message_summary(result.outbound_message) if result.outbound_message else None,
            refused=result.refused,
            refusal_category=result.refusal_category,
            emotion_score=result.emotion_score,
            handoff_triggered=result.handoff_event is not None,
        )

    async def event_generator():
        queue: asyncio.Queue[str | None] = asyncio.Queue()

        async def on_chunk_impl(text: str) -> None:
            await queue.put(text)

        async def run_turn():
            result = await manager.handle_turn(session, body.content, on_chunk=on_chunk_impl)
            await queue.put(None)
            return result

        task = asyncio.create_task(run_turn())
        while True:
            item = await queue.get()
            if item is None:
                break
            yield {"event": "token", "data": item}

        result = await task
        yield {
            "event": "done",
            "data": TurnResponse(
                outbound_message=_message_summary(result.outbound_message) if result.outbound_message else None,
                refused=result.refused,
                refusal_category=result.refusal_category,
                emotion_score=result.emotion_score,
                handoff_triggered=result.handoff_event is not None,
            ).model_dump_json(),
        }

    return EventSourceResponse(event_generator())


@router.post("/{session_id}/resume", response_model=TurnResponse)
async def resume_session(
    session_id: str,
    ctx: AppContext = Depends(get_ctx),
    repository: ConversationRepository = Depends(get_repository),
) -> TurnResponse:
    """Re-checks a HANDED_OFF session's paused Workflow Engine instance and
    relays the final answer back into the conversation once Human
    Oversight's real decision-callback dispatcher has resumed it to
    completion (ticket #82). A no-op call (still paused, or this session
    was never routed through Workflow Engine at all) is a 409, not an
    error -- the caller (a human reviewer's own follow-up, or a client
    polling after an escalation message) is expected to retry."""
    session = await repository.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")

    manager = build_session_manager(ctx, repository)
    result = await manager.resume_from_workflow(session)
    if result is None:
        raise HTTPException(status_code=409, detail="nothing to resume: instance still paused or not workflow-routed")

    return TurnResponse(
        outbound_message=_message_summary(result.outbound_message) if result.outbound_message else None,
        refused=result.refused,
        refusal_category=result.refusal_category,
        emotion_score=result.emotion_score,
        handoff_triggered=result.handoff_event is not None,
    )


@router.post("/{session_id}/handoff", response_model=HandoffResponse)
async def handoff(
    session_id: str,
    body: HandoffRequest,
    ctx: AppContext = Depends(get_ctx),
    repository: ConversationRepository = Depends(get_repository),
) -> HandoffResponse:
    session = await repository.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    if session.status != SessionStatus.ACTIVE:
        raise HTTPException(status_code=409, detail=f"cannot hand off a session in status {session.status.value}")

    manager = build_session_manager(ctx, repository)
    event = await manager.manual_handoff(session, body.reason)
    return HandoffResponse(status="handed_off", handoff_event_id=event.id)


@router.post("/{session_id}/close", response_model=StatusResponse)
async def close_session(
    session_id: str,
    repository: ConversationRepository = Depends(get_repository),
) -> StatusResponse:
    session = await repository.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    if session.status == SessionStatus.CLOSED:
        return StatusResponse(status=session.status.value)
    session.status = SessionStatus.CLOSED
    session.last_activity_at = now()
    session = await repository.update_session(session)
    return StatusResponse(status=session.status.value)
