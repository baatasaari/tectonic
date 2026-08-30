"""`/v1/conversational-engine/sessions` routes (LLD §3.3, §3.4)."""
from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sse_starlette.sse import EventSourceResponse

from conversational_engine.api.deps import build_session_manager, get_ctx, get_repository
from conversational_engine.app_context import AppContext
from conversational_engine.core.domain import Channel, SessionStatus, now
from conversational_engine.core.ports import ConversationRepository
from conversational_engine.schemas.sessions import (
    CreateSessionRequest,
    CreateSessionResponse,
    HandoffEventSummary,
    HandoffRequest,
    HandoffResponse,
    MessageSummary,
    SendMessageRequest,
    SessionDetail,
    SessionExport,
    SessionListResponse,
    SessionSummary,
    StatusResponse,
    TurnResponse,
)

router = APIRouter(prefix="/v1/conversational-engine/sessions", tags=["sessions"])


def _tenant_id(request: Request, ctx: AppContext) -> str:
    return request.headers.get("X-Tenant-Id", ctx.settings.tenant_id)


def _reject_null_byte_query(**params: str | None) -> None:
    """A raw `Query()` string parameter never runs through a Pydantic body
    field's own NUL-byte validator -- ticket #82's platform-wide sweep
    established this same guard on every other module's own list/search
    routes; applied here too since this is a newly-added route of the same
    shape (`GET` list with free-text filters)."""
    for name, value in params.items():
        if value is not None and "\x00" in value:
            raise HTTPException(status_code=422, detail=f"{name} must not contain a NUL byte")


def _message_summary(m) -> MessageSummary:
    return MessageSummary(
        id=m.id, direction=m.direction.value, content=m.content, emotion_score=m.emotion_score, created_at=m.created_at
    )


def _session_detail(session, messages) -> SessionDetail:
    return SessionDetail(
        id=session.id,
        tenant_id=session.tenant_id,
        channel=session.channel.value,
        status=session.status.value,
        persona_config_ref=session.persona_config_ref,
        trace_id=session.trace_id,
        user_ref=session.user_ref,
        created_at=session.created_at,
        last_activity_at=session.last_activity_at,
        messages=[_message_summary(m) for m in messages],
    )


def _session_summary(session) -> SessionSummary:
    return SessionSummary(
        id=session.id,
        tenant_id=session.tenant_id,
        channel=session.channel.value,
        status=session.status.value,
        persona_config_ref=session.persona_config_ref,
        user_ref=session.user_ref,
        created_at=session.created_at,
        last_activity_at=session.last_activity_at,
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


@router.get("", response_model=SessionListResponse)
async def list_sessions(
    request: Request,
    status: str | None = Query(None),
    channel: str | None = Query(None),
    user_ref: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ctx: AppContext = Depends(get_ctx),
    repository: ConversationRepository = Depends(get_repository),
) -> SessionListResponse:
    """Session list/search — independent architecture assessment's Phase 2
    exit bar. Always tenant-scoped (§3.4's own "every request carries...
    tenant... context" contract): the caller can further narrow by status,
    channel, or a specific returning user's own `user_ref`, but never sees
    another tenant's sessions."""
    _reject_null_byte_query(status=status, channel=channel, user_ref=user_ref)
    tenant_id = _tenant_id(request, ctx)
    sessions, total = await repository.list_sessions(
        tenant_id, status=status, channel=channel, user_ref=user_ref, limit=limit, offset=offset,
    )
    return SessionListResponse(items=[_session_summary(s) for s in sessions], total=total, limit=limit, offset=offset)


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session(
    session_id: str,
    repository: ConversationRepository = Depends(get_repository),
) -> SessionDetail:
    session = await repository.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    messages = await repository.list_messages(session_id)
    return _session_detail(session, messages)


@router.get("/{session_id}/export", response_model=SessionExport)
async def export_session(
    session_id: str,
    repository: ConversationRepository = Depends(get_repository),
) -> SessionExport:
    """Full transcript export for one session — independent architecture
    assessment's Phase 2 exit bar. See `SessionExport`'s own docstring for
    scope: this module's own records only, not a cross-platform privacy
    export (Long-Term Memory's own consent/erasure surface is the
    separately-scoped place for that)."""
    session = await repository.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    messages = await repository.list_messages(session_id)
    handoff_events = await repository.list_handoff_events(session_id)
    return SessionExport(
        session=_session_detail(session, messages),
        handoff_events=[
            HandoffEventSummary(id=e.id, trigger_reason=e.trigger_reason.value, target=e.target, created_at=e.created_at)
            for e in handoff_events
        ],
        exported_at=datetime.now(UTC),
    )


@router.delete("/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    repository: ConversationRepository = Depends(get_repository),
) -> None:
    """Independent architecture assessment's Phase 2 exit bar
    ("session... delete"). Hard-deletes this module's own record of the
    session (and its messages/handoff events) — see
    `ConversationRepository.delete_session`'s own docstring for why this is
    scoped to this module's own data, not a cross-platform privacy erasure.
    Idempotent: deleting an already-gone or never-existing session is not
    an error — the caller's desired end state (this session's data does
    not exist) already holds."""
    await repository.delete_session(session_id)


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
