"""In-memory fakes for the ports in core/ports.py — the unit-test tier,
mirroring the other modules' core/fakes.py. Notification channels are
mocked here per the LLD's own Integration testing row ("notification
channels mocked").
"""
from __future__ import annotations

import copy
from datetime import datetime

from human_oversight.core.domain import (
    DecisionRecord,
    NotificationLogRecord,
    OverrideRecord,
    OversightRequestRecord,
    RequestStatus,
    new_id,
    now,
)


class InMemoryHumanOversightRepository:
    def __init__(self) -> None:
        self.requests: dict[str, OversightRequestRecord] = {}
        self.decisions: dict[str, DecisionRecord] = {}  # keyed by request_id
        self.overrides: dict[str, OverrideRecord] = {}  # keyed by decision_id
        self.notification_logs: list[NotificationLogRecord] = []

    async def create_request(self, record: OversightRequestRecord) -> OversightRequestRecord:
        self.requests[record.id] = copy.deepcopy(record)
        return copy.deepcopy(record)

    async def get_request(self, tenant_id: str, request_id: str) -> OversightRequestRecord | None:
        rec = self.requests.get(request_id)
        if rec is None or rec.tenant_id != tenant_id:
            return None
        return copy.deepcopy(rec)

    async def update_request(self, record: OversightRequestRecord) -> OversightRequestRecord:
        self.requests[record.id] = copy.deepcopy(record)
        return copy.deepcopy(record)

    async def list_requests(self, tenant_id: str, status: str | None = None) -> list[OversightRequestRecord]:
        return [
            copy.deepcopy(r) for r in self.requests.values()
            if r.tenant_id == tenant_id and (status is None or r.status.value == status)
        ]

    async def list_pending_expired(self, tenant_id: str, as_of: datetime) -> list[OversightRequestRecord]:
        return [
            copy.deepcopy(r) for r in self.requests.values()
            if r.tenant_id == tenant_id and r.status in (RequestStatus.PENDING, RequestStatus.CLAIMED)
            and r.expires_at <= as_of
        ]

    async def create_decision(self, record: DecisionRecord) -> DecisionRecord:
        self.decisions[record.request_id] = copy.deepcopy(record)
        return copy.deepcopy(record)

    async def get_decision_for_request(self, request_id: str) -> DecisionRecord | None:
        rec = self.decisions.get(request_id)
        return copy.deepcopy(rec) if rec else None

    async def create_override_record(self, record: OverrideRecord) -> OverrideRecord:
        self.overrides[record.decision_id] = copy.deepcopy(record)
        return copy.deepcopy(record)

    async def get_override_for_decision(self, decision_id: str) -> OverrideRecord | None:
        rec = self.overrides.get(decision_id)
        return copy.deepcopy(rec) if rec else None

    async def create_notification_log(self, record: NotificationLogRecord) -> NotificationLogRecord:
        self.notification_logs.append(copy.deepcopy(record))
        return copy.deepcopy(record)


class InMemoryNotificationChannel:
    def __init__(self, name: str = "test-channel", should_fail: bool = False) -> None:
        self.name = name
        self.should_fail = should_fail
        self.sent: list[OversightRequestRecord] = []

    async def send(self, request: OversightRequestRecord) -> NotificationLogRecord:
        self.sent.append(request)
        status = "failed" if self.should_fail else "delivered"
        return NotificationLogRecord(
            id=new_id(), request_id=request.id, channel=self.name,
            delivered_at=None if self.should_fail else now(), delivery_status=status,
        )


class StubDecisionCallbackDispatcher:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def notify(self, requesting_module: str, requesting_ref: str, decision: DecisionRecord) -> None:
        self.calls.append({
            "requesting_module": requesting_module, "requesting_ref": requesting_ref,
            "decision": decision.decision.value, "decided_by": decision.decided_by,
        })


class StubAuditabilityClient:
    def __init__(self) -> None:
        self.events: list[dict] = []

    async def emit(self, event: dict) -> None:
        self.events.append(copy.deepcopy(event))
