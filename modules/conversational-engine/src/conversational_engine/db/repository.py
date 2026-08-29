"""SQLAlchemy-backed implementation of ConversationRepository (LLD §3.1)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from conversational_engine.core.domain import (
    Channel,
    ConversationSessionRecord,
    HandoffEventRecord,
    HandoffTriggerReason,
    MessageDirection,
    MessageRecord,
    PersonaConfigRecord,
    SessionStatus,
)
from conversational_engine.db import models


def _session_to_domain(m: models.ConversationSession) -> ConversationSessionRecord:
    return ConversationSessionRecord(
        id=str(m.id),
        tenant_id=m.tenant_id,
        channel=Channel(m.channel),
        trace_id=m.trace_id,
        user_ref=m.user_ref,
        status=SessionStatus(m.status),
        persona_config_ref=m.persona_config_ref,
        created_at=m.created_at,
        last_activity_at=m.last_activity_at,
    )


def _message_to_domain(m: models.Message) -> MessageRecord:
    return MessageRecord(
        id=str(m.id),
        session_id=str(m.session_id),
        direction=MessageDirection(m.direction),
        content=m.content,
        emotion_score=m.emotion_score,
        guardrail_check_result=m.guardrail_check_result,
        created_at=m.created_at,
    )


def _handoff_to_domain(m: models.HandoffEvent) -> HandoffEventRecord:
    return HandoffEventRecord(
        id=str(m.id),
        session_id=str(m.session_id),
        trigger_reason=HandoffTriggerReason(m.trigger_reason),
        target=m.target,
        created_at=m.created_at,
    )


def _persona_to_domain(m: models.PersonaConfig) -> PersonaConfigRecord:
    return PersonaConfigRecord(
        id=str(m.id),
        tenant_id=m.tenant_id,
        name=m.name,
        tone_settings=dict(m.tone_settings or {}),
        allowed_topics=list(m.allowed_topics or []),
        denied_topics=list(m.denied_topics or []),
    )


class SQLAlchemyConversationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_session(self, record: ConversationSessionRecord) -> ConversationSessionRecord:
        m = models.ConversationSession(
            id=record.id,
            tenant_id=record.tenant_id,
            channel=record.channel.value,
            user_ref=record.user_ref,
            status=record.status.value,
            persona_config_ref=record.persona_config_ref,
            trace_id=record.trace_id,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _session_to_domain(m)

    async def get_session(self, session_id: str) -> ConversationSessionRecord | None:
        m = await self.session.get(models.ConversationSession, session_id)
        return _session_to_domain(m) if m else None

    async def update_session(self, record: ConversationSessionRecord) -> ConversationSessionRecord:
        m = await self.session.get(models.ConversationSession, record.id)
        if m is None:
            raise LookupError(record.id)
        m.status = record.status.value
        m.persona_config_ref = record.persona_config_ref
        m.last_activity_at = record.last_activity_at
        await self.session.commit()
        await self.session.refresh(m)
        return _session_to_domain(m)

    async def append_message(self, record: MessageRecord) -> MessageRecord:
        m = models.Message(
            id=record.id,
            session_id=record.session_id,
            direction=record.direction.value,
            content=record.content,
            emotion_score=record.emotion_score,
            guardrail_check_result=record.guardrail_check_result,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _message_to_domain(m)

    async def list_messages(self, session_id: str) -> list[MessageRecord]:
        rows = await self.session.execute(
            select(models.Message).where(models.Message.session_id == session_id).order_by(models.Message.created_at)
        )
        return [_message_to_domain(m) for m in rows.scalars().all()]

    async def create_handoff_event(self, record: HandoffEventRecord) -> HandoffEventRecord:
        m = models.HandoffEvent(
            id=record.id, session_id=record.session_id, trigger_reason=record.trigger_reason.value, target=record.target
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _handoff_to_domain(m)

    async def get_latest_handoff_event(self, session_id: str) -> HandoffEventRecord | None:
        row = await self.session.execute(
            select(models.HandoffEvent)
            .where(models.HandoffEvent.session_id == session_id)
            .order_by(models.HandoffEvent.created_at.desc())
            .limit(1)
        )
        m = row.scalar_one_or_none()
        return _handoff_to_domain(m) if m is not None else None

    async def get_persona_config(self, persona_config_ref: str, tenant_id: str) -> PersonaConfigRecord | None:
        m = await self.session.get(models.PersonaConfig, persona_config_ref)
        if m is None or m.tenant_id not in (tenant_id, "*"):
            return None
        return _persona_to_domain(m)
