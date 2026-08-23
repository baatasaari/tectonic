"""Abstract ports this module depends on: persistence, pluggable
notification channels, the decision callback destination, and
Auditability."""
from __future__ import annotations

from typing import Protocol

from human_oversight.core.domain import (
    DecisionRecord,
    NotificationLogRecord,
    OverrideRecord,
    OversightRequestRecord,
)


class HumanOversightRepository(Protocol):
    async def create_request(self, record: OversightRequestRecord) -> OversightRequestRecord: ...

    async def get_request(self, tenant_id: str, request_id: str) -> OversightRequestRecord | None: ...

    async def update_request(self, record: OversightRequestRecord) -> OversightRequestRecord: ...

    async def list_requests(self, tenant_id: str, status: str | None = None) -> list[OversightRequestRecord]: ...

    async def list_pending_expired(self, tenant_id: str, as_of) -> list[OversightRequestRecord]: ...

    async def create_decision(self, record: DecisionRecord) -> DecisionRecord: ...

    async def get_decision_for_request(self, request_id: str) -> DecisionRecord | None: ...

    async def create_override_record(self, record: OverrideRecord) -> OverrideRecord: ...

    async def get_override_for_decision(self, decision_id: str) -> OverrideRecord | None: ...

    async def create_notification_log(self, record: NotificationLogRecord) -> NotificationLogRecord: ...


class NotificationChannel(Protocol):
    async def send(self, request: OversightRequestRecord) -> NotificationLogRecord: ...


class DecisionCallbackDispatcher(Protocol):
    async def notify(self, requesting_module: str, requesting_ref: str, decision: DecisionRecord) -> None: ...


class AuditabilityClient(Protocol):
    async def emit(self, event: dict) -> None: ...
