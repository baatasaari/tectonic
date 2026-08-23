"""Decision Capture + Override Logger (LLD §2 sub-components, §Level 3
"Sequence: override with reasoning captured"): records the human's
decision, triggers the callback to the requesting module, and — for an
override — logs the original proposal vs. the human's action with
additional audit weight.
"""
from __future__ import annotations

from typing import Any

from human_oversight.core.domain import (
    DecisionRecord,
    DecisionType,
    OverrideRecord,
    RequestNotDecidableError,
    RequestNotFoundError,
    RequestStatus,
    new_id,
)
from human_oversight.core.ports import (
    AuditabilityClient,
    DecisionCallbackDispatcher,
    HumanOversightRepository,
)


class DecisionCapture:
    def __init__(
        self, repository: HumanOversightRepository, callback_dispatcher: DecisionCallbackDispatcher,
        auditability: AuditabilityClient,
    ) -> None:
        self._repository = repository
        self._callback_dispatcher = callback_dispatcher
        self._auditability = auditability

    async def capture(
        self, tenant_id: str, request_id: str, *, decision: str, decided_by: str, decision_reason: str = "",
        override_details: dict[str, Any] | None = None,
    ) -> DecisionRecord:
        request = await self._repository.get_request(tenant_id, request_id)
        if request is None:
            raise RequestNotFoundError(request_id)
        if request.status not in (RequestStatus.PENDING, RequestStatus.CLAIMED):
            raise RequestNotDecidableError(request_id, request.status.value)

        decision_type = DecisionType(decision)
        record = DecisionRecord(
            id=new_id(), request_id=request_id, decision=decision_type, decided_by=decided_by,
            decision_reason=decision_reason,
        )
        record = await self._repository.create_decision(record)

        if decision_type == DecisionType.OVERRIDE:
            details = override_details or {}
            override = OverrideRecord(
                id=new_id(), decision_id=record.id,
                original_agent_proposal=details.get("original_agent_proposal", {}),
                human_override_action=details.get("human_override_action", {}),
                override_reason=details.get("override_reason", decision_reason),
            )
            await self._repository.create_override_record(override)
            await self._auditability.emit(
                {
                    "event": "oversight_override", "tenant_id": tenant_id, "request_id": request_id,
                    "decision_id": record.id, "original_agent_proposal": override.original_agent_proposal,
                    "human_override_action": override.human_override_action, "override_reason": override.override_reason,
                }
            )

        request.status = RequestStatus.DECIDED
        await self._repository.update_request(request)

        await self._callback_dispatcher.notify(request.requesting_module, request.requesting_ref, record)
        await self._auditability.emit(
            {
                "event": "oversight_decision", "tenant_id": tenant_id, "request_id": request_id,
                "decision": decision_type.value, "decided_by": decided_by,
            }
        )
        return record
