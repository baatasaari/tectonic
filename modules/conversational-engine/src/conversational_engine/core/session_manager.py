"""Session Manager (LLD §2.2, §3.4, §3.5): owns session lifecycle,
coordinates the turn — the module's central orchestrator, analogous to
Module 1's Execution Scheduler. Delegates generation to LLM Gateway,
moderation to Guardrails, escalation policy to the Handoff Trigger Engine;
it does not duplicate any of their logic, per the module's stated purpose.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import replace

from conversational_engine.config import ConversationalEngineSettings
from conversational_engine.core.domain import (
    Channel,
    ConversationSessionRecord,
    HandoffEventRecord,
    HandoffTriggerReason,
    MessageDirection,
    MessageRecord,
    PersonaConfigRecord,
    SessionStatus,
    TurnResult,
    new_id,
    now,
)
from conversational_engine.core.emotion import EmotionUrgencyDetector
from conversational_engine.core.handoff import HandoffTriggerEngine
from conversational_engine.core.persona import PersonaEngine
from conversational_engine.core.ports import (
    AuditabilityClient,
    ConversationRepository,
    GuardrailsClient,
    HumanOversightClient,
    LLMGatewayClient,
    ObservabilityClient,
    SessionStateStore,
    WorkflowEngineClient,
)
from conversational_engine.core.refusal import RefusalComposer
from conversational_engine.telemetry.logging import get_logger

logger = get_logger(component="session_manager")

_HANDOFF_PHRASES = (
    "speak to a human",
    "speak to someone",
    "talk to a person",
    "talk to a human",
    "human agent",
    "real person",
    "speak with an agent",
    "connect me to an agent",
)


def _is_explicit_handoff_request(text: str) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in _HANDOFF_PHRASES)


_DEFAULT_PERSONA = PersonaConfigRecord(id="default", tenant_id="*", name="default")

# The step id `support-agent-v1` uses for its own final answer-composing
# step (docs/phase2-product-slice-01-support-agent.md) -- a real, if
# narrow, contract between this module and that one workflow definition;
# a differently-shaped definition run through this same path would need
# its own extraction convention.
_RESPOND_STEP_ID = "respond"

# Prefix a WORKFLOW_ESCALATION handoff event's own `target` field carries,
# so `resume_from_workflow` below can recover the paused instance id it
# needs to poll -- kept as one shared constant with the write site in
# `_handle_turn_via_workflow_engine` rather than duplicating the string.
_WORKFLOW_INSTANCE_TARGET_PREFIX = "workflow-instance:"


def _extract_workflow_response_content(context: dict) -> str:
    step_output = context.get(_RESPOND_STEP_ID)
    if isinstance(step_output, dict) and isinstance(step_output.get("content"), str):
        return step_output["content"]
    return "I'm sorry, I wasn't able to put together an answer for that."


class SessionManager:
    def __init__(
        self,
        repository: ConversationRepository,
        state_store: SessionStateStore,
        llm_gateway: LLMGatewayClient,
        guardrails: GuardrailsClient,
        human_oversight: HumanOversightClient,
        observability: ObservabilityClient,
        auditability: AuditabilityClient,
        settings: ConversationalEngineSettings,
        workflow_engine: WorkflowEngineClient | None = None,
    ) -> None:
        self.repository = repository
        self.state_store = state_store
        self.llm_gateway = llm_gateway
        self.guardrails = guardrails
        self.human_oversight = human_oversight
        self.observability = observability
        self.auditability = auditability
        self.settings = settings
        self.workflow_engine = workflow_engine
        self.emotion_detector = EmotionUrgencyDetector(llm_gateway)
        self.persona_engine = PersonaEngine()
        self.refusal_composer = RefusalComposer()
        self.handoff_engine = HandoffTriggerEngine(settings.handoff)

    async def create_session(
        self, *, tenant_id: str, channel: Channel, persona_config_ref: str, trace_id: str, user_ref: str | None = None
    ) -> ConversationSessionRecord:
        record = ConversationSessionRecord(
            id=new_id(),
            tenant_id=tenant_id,
            channel=channel,
            trace_id=trace_id,
            user_ref=user_ref,
            persona_config_ref=persona_config_ref or self.settings.persona.default_persona_config_ref,
        )
        return await self.repository.create_session(record)

    async def handle_turn(
        self,
        session: ConversationSessionRecord,
        message_content: str,
        *,
        on_chunk: Callable[[str], Awaitable[None]] | None = None,
    ) -> TurnResult:
        if self.settings.workflow_routing.enabled and self.workflow_engine is not None:
            return await self._handle_turn_via_workflow_engine(session, message_content)

        tenant_id = session.tenant_id
        trace_id = session.trace_id

        emotion_score = await self.emotion_detector.score(message_content, tenant_id)
        await self.repository.append_message(
            MessageRecord(
                id=new_id(),
                session_id=session.id,
                direction=MessageDirection.INBOUND,
                content=message_content,
                emotion_score=emotion_score,
            )
        )

        persona = await self.repository.get_persona_config(session.persona_config_ref, tenant_id) or _DEFAULT_PERSONA
        history = await self.repository.list_messages(session.id)

        state = await self.state_store.get(session.id) or {}
        consecutive_refusals = int(state.get("consecutive_refusals", 0))

        build_result = self.persona_engine.build_prompt(persona, history, message_content)
        if build_result.denied_topic is not None:
            outbound, refusal_category = await self._refuse(
                session, "denied_topic", build_result.denied_topic
            )
            consecutive_refusals += 1
        else:
            full_text_parts: list[str] = []
            async for chunk in self.llm_gateway.stream_complete(
                prompt_context=build_result.prompt_context, tenant_id=tenant_id, trace_id=trace_id
            ):
                full_text_parts.append(chunk)
                if on_chunk is not None:
                    await on_chunk(chunk)
            full_text = "".join(full_text_parts)

            allowed, decision = await self.guardrails.check(
                content={"output": full_text}, policy_profile="conversational_default", tenant_id=tenant_id
            )
            if not allowed:
                category = decision.get("violation_category", "policy_violation")
                outbound, refusal_category = await self._refuse(session, category, decision.get("detail", ""))
                consecutive_refusals += 1
            else:
                outbound = await self.repository.append_message(
                    MessageRecord(
                        id=new_id(),
                        session_id=session.id,
                        direction=MessageDirection.OUTBOUND,
                        content=full_text,
                        guardrail_check_result=decision,
                    )
                )
                refusal_category = None
                consecutive_refusals = 0

        handoff_decision = self.handoff_engine.evaluate(
            emotion_score=emotion_score,
            explicit_request=_is_explicit_handoff_request(message_content),
            consecutive_refusals=consecutive_refusals,
        )
        handoff_event = None
        if handoff_decision.trigger and session.status == SessionStatus.ACTIVE:
            handoff_event = await self._trigger_handoff(session, handoff_decision.reason, emotion_score)
            session = replace(session, status=SessionStatus.HANDED_OFF)

        await self.state_store.set(
            session.id, {"consecutive_refusals": consecutive_refusals}, self.settings.session.ttl_seconds
        )
        session = replace(session, last_activity_at=now())
        await self.repository.update_session(session)

        await self.observability.emit(
            {
                "event_type": "conversation.turn.completed" if refusal_category is None else "conversation.turn.refused",
                "session_id": session.id,
                "tenant_id": tenant_id,
                "trace_id": trace_id,
                "channel": session.channel.value,
                "emotion_score": emotion_score,
            }
        )

        return TurnResult(
            outbound_message=outbound,
            refused=refusal_category is not None,
            refusal_category=refusal_category,
            emotion_score=emotion_score,
            handoff_event=handoff_event,
        )

    async def _handle_turn_via_workflow_engine(
        self, session: ConversationSessionRecord, message_content: str
    ) -> TurnResult:
        """Phase 2 support-agent slice (ticket #82): routes the turn through
        Workflow Engine's own `support-agent-v1` definition (intent ->
        retrieve-or-tool-call -> guardrail -> respond-or-escalate) instead of
        calling LLM Gateway directly. Only reached when
        `settings.workflow_routing.enabled` is set — every other tenant/
        deployment keeps the pre-existing direct path untouched.

        Streaming (`on_chunk`) isn't supported on this path: Workflow
        Engine's own `/instances` call runs the whole graph synchronously
        and returns one final result, not a token stream — a real,
        documented simplification of this path, not a bug; the streaming
        direct-LLM-Gateway path above is unaffected for every tenant not
        opted into workflow routing.
        """
        tenant_id = session.tenant_id
        assert self.workflow_engine is not None  # guarded by the caller

        await self.repository.append_message(
            MessageRecord(
                id=new_id(), session_id=session.id, direction=MessageDirection.INBOUND, content=message_content,
            )
        )

        result = await self.workflow_engine.start_instance(
            definition_id=self.settings.workflow_routing.definition_id,
            initial_context={"message": message_content},
            tenant_id=tenant_id,
        )

        handoff_event: HandoffEventRecord | None = None
        refusal_category: str | None = None
        status = result.get("status")

        if status == "paused_for_approval":
            # Workflow Engine's own refund-threshold symbolic step (or any
            # future business-rule escalation) paused this instance for a
            # real Human Oversight review -- a genuinely different trigger
            # than this module's own emotion/keyword-based HandoffTriggerEngine,
            # so it's recorded with its own HandoffTriggerReason rather than
            # reusing EXPLICIT/EMOTION/REPEATED_REFUSAL.
            text = "I've escalated this to a specialist for review — they'll follow up shortly."
            outbound = await self.repository.append_message(
                MessageRecord(id=new_id(), session_id=session.id, direction=MessageDirection.OUTBOUND, content=text)
            )
            event = HandoffEventRecord(
                id=new_id(), session_id=session.id, trigger_reason=HandoffTriggerReason.WORKFLOW_ESCALATION,
                target=f"{_WORKFLOW_INSTANCE_TARGET_PREFIX}{result.get('id')}",
            )
            handoff_event = await self.repository.create_handoff_event(event)
            await self.auditability.emit(
                {
                    "event_type": "conversation.handoff",
                    "session_id": session.id,
                    "tenant_id": tenant_id,
                    "trigger_reason": HandoffTriggerReason.WORKFLOW_ESCALATION.value,
                    "workflow_instance_id": result.get("id"),
                }
            )
            session = replace(session, status=SessionStatus.HANDED_OFF)
        elif status == "completed":
            content = _extract_workflow_response_content(result.get("context", {}))
            outbound = await self.repository.append_message(
                MessageRecord(id=new_id(), session_id=session.id, direction=MessageDirection.OUTBOUND, content=content)
            )
        else:
            outbound, refusal_category = await self._refuse(session, "workflow_failed", str(status))

        session = replace(session, last_activity_at=now())
        await self.repository.update_session(session)

        await self.observability.emit(
            {
                "event_type": "conversation.turn.completed" if refusal_category is None else "conversation.turn.refused",
                "session_id": session.id,
                "tenant_id": tenant_id,
                "trace_id": result.get("trace_id", session.trace_id),
                "channel": session.channel.value,
                "workflow_instance_id": result.get("id"),
            }
        )

        return TurnResult(
            outbound_message=outbound,
            refused=refusal_category is not None,
            refusal_category=refusal_category,
            emotion_score=0.0,
            handoff_event=handoff_event,
        )

    async def resume_from_workflow(self, session: ConversationSessionRecord) -> TurnResult | None:
        """Re-checks a HANDED_OFF session's paused Workflow Engine instance
        and, if Human Oversight's own real decision-callback dispatcher has
        since resumed it to completion, relays the final answer back into
        the conversation and reactivates the session (ticket #82's own
        Definition of Done item 7: "the reviewer's real decision resumes
        the conversation correctly"). Genuine module-level gap this ticket
        surfaced: `_handle_turn_via_workflow_engine` above only ever
        recorded the escalation and stopped -- nothing previously polled
        the paused instance again, so a resolved approval had no way back
        into the conversation at all. Returns None when there is nothing
        to relay yet (instance still paused, or this session was never
        actually waiting on one) -- callers should treat that as "no
        change", not an error; the API route below maps it to a 409."""
        if session.status != SessionStatus.HANDED_OFF or self.workflow_engine is None:
            return None

        event = await self.repository.get_latest_handoff_event(session.id)
        if event is None or event.trigger_reason != HandoffTriggerReason.WORKFLOW_ESCALATION:
            return None
        if not event.target.startswith(_WORKFLOW_INSTANCE_TARGET_PREFIX):
            return None
        instance_id = event.target[len(_WORKFLOW_INSTANCE_TARGET_PREFIX) :]

        result = await self.workflow_engine.get_instance(instance_id=instance_id, tenant_id=session.tenant_id)
        if result.get("status") != "completed":
            return None

        content = _extract_workflow_response_content(result.get("context", {}))
        outbound = await self.repository.append_message(
            MessageRecord(id=new_id(), session_id=session.id, direction=MessageDirection.OUTBOUND, content=content)
        )
        session = replace(session, status=SessionStatus.ACTIVE, last_activity_at=now())
        await self.repository.update_session(session)

        await self.observability.emit(
            {
                "event_type": "conversation.turn.completed",
                "session_id": session.id,
                "tenant_id": session.tenant_id,
                "trace_id": result.get("trace_id", session.trace_id),
                "channel": session.channel.value,
                "workflow_instance_id": instance_id,
            }
        )

        return TurnResult(
            outbound_message=outbound, refused=False, refusal_category=None, emotion_score=0.0, handoff_event=None,
        )

    async def _refuse(
        self, session: ConversationSessionRecord, category: str, detail: str
    ) -> tuple[MessageRecord, str]:
        text = self.refusal_composer.compose(category, detail)
        outbound = await self.repository.append_message(
            MessageRecord(
                id=new_id(),
                session_id=session.id,
                direction=MessageDirection.OUTBOUND,
                content=text,
                guardrail_check_result={"violation_category": category, "detail": detail},
            )
        )
        return outbound, category

    async def _trigger_handoff(
        self, session: ConversationSessionRecord, reason: HandoffTriggerReason, emotion_score: float, detail: str = ""
    ) -> HandoffEventRecord:
        ref_id = await self.human_oversight.request_handoff(
            session_id=session.id,
            trigger_reason=reason.value,
            context={"emotion_score": emotion_score, "detail": detail},
            tenant_id=session.tenant_id,
        )
        event = HandoffEventRecord(
            id=new_id(), session_id=session.id, trigger_reason=reason, target=f"human:{ref_id}"
        )
        event = await self.repository.create_handoff_event(event)
        await self.auditability.emit(
            {
                "event_type": "conversation.handoff",
                "session_id": session.id,
                "tenant_id": session.tenant_id,
                "trigger_reason": reason.value,
                "detail": detail,
                "human_oversight_ref": ref_id,
            }
        )
        return event

    async def manual_handoff(self, session: ConversationSessionRecord, reason: str) -> HandoffEventRecord:
        """Operator/user-triggered handoff via the API — always recorded as
        an explicit trigger; `reason` is free text carried into the audit
        event detail rather than forced into the fixed trigger-reason enum."""
        event = await self._trigger_handoff(session, HandoffTriggerReason.EXPLICIT, emotion_score=0.0, detail=reason)
        session = replace(session, status=SessionStatus.HANDED_OFF, last_activity_at=now())
        await self.repository.update_session(session)
        return event
