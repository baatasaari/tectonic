"""Notification channel adapters and the decision callback dispatcher.

**Notification channels.** Slack and MS Teams delivery are, under the
hood, just an HTTP POST to a per-workspace incoming-webhook URL — these
adapters are genuinely functional given a real webhook URL configured,
not stand-ins. Email is the one channel needing a real SMTP server this
build environment doesn't have; `SMTPNotificationChannel` is real code
(stdlib `smtplib`) but isn't exercised end-to-end here, matching this
module's own LLD testing plan ("notification channels mocked").

**Decision callback.** Workflow Engine (Module 1) already has a real,
built `POST /instances/{id}/approvals/{approval_id}/callback` endpoint —
`requesting_ref` for a Workflow-Engine-originated request is expected as
`"{instance_id}:{approval_id}"` so this dispatcher can call it for real.
Every other requesting module doesn't define a standard callback
endpoint yet; those get a best-effort generic callback (logged, not
raised, on failure) — the same documented-gap pattern used elsewhere in
this platform (see the module README).

Every client below is a `ResilientHTTPClient` (retry + circuit breaker on
every outbound call — see resilience.py). The webhook-based channels pass
an absolute per-call URL (`self._webhook_url`) to `_post` rather than a
fixed `base_url` — httpx treats an absolute URL passed to a request call
as-is regardless of the client's configured `base_url`, so this works the
same way it did before.
"""
from __future__ import annotations

import smtplib
from email.message import EmailMessage

import httpx

from human_oversight.clients.resilience import CircuitBreakerError, ResilientHTTPClient
from human_oversight.core.domain import (
    DecisionRecord,
    NotificationLogRecord,
    OversightRequestRecord,
    new_id,
    now,
)
from human_oversight.telemetry.logging import get_logger

logger = get_logger(component="http_clients")

_VERY_SHORT_TIMEOUT = httpx.Timeout(connect=5.0, read=5.0, write=5.0, pool=5.0)


class WebhookNotificationChannel(ResilientHTTPClient):
    def __init__(self, webhook_url: str, client: httpx.AsyncClient | None = None) -> None:
        super().__init__("", client=client, breaker_name="webhook-notification")
        self._webhook_url = webhook_url

    async def send(self, request: OversightRequestRecord) -> NotificationLogRecord:
        try:
            await self._post(self._webhook_url, json={"request_id": request.id, "priority": request.priority})
            status = "delivered"
        except (httpx.HTTPError, CircuitBreakerError):
            status = "failed"
        return NotificationLogRecord(
            id=new_id(), request_id=request.id, channel="webhook", delivered_at=now() if status == "delivered" else None,
            delivery_status=status,
        )


class SlackNotificationChannel(ResilientHTTPClient):
    def __init__(self, webhook_url: str, client: httpx.AsyncClient | None = None) -> None:
        super().__init__("", client=client, breaker_name="slack-notification")
        self._webhook_url = webhook_url

    async def send(self, request: OversightRequestRecord) -> NotificationLogRecord:
        text = f"New oversight request ({request.priority}) from {request.requesting_module}: {request.id}"
        try:
            await self._post(self._webhook_url, json={"text": text})
            status = "delivered"
        except (httpx.HTTPError, CircuitBreakerError):
            status = "failed"
        return NotificationLogRecord(
            id=new_id(), request_id=request.id, channel="slack", delivered_at=now() if status == "delivered" else None,
            delivery_status=status,
        )


class TeamsNotificationChannel(ResilientHTTPClient):
    def __init__(self, webhook_url: str, client: httpx.AsyncClient | None = None) -> None:
        super().__init__("", client=client, breaker_name="teams-notification")
        self._webhook_url = webhook_url

    async def send(self, request: OversightRequestRecord) -> NotificationLogRecord:
        card = {
            "@type": "MessageCard", "@context": "http://schema.org/extensions",
            "summary": "New oversight request",
            "text": f"New oversight request ({request.priority}) from {request.requesting_module}: {request.id}",
        }
        try:
            await self._post(self._webhook_url, json=card)
            status = "delivered"
        except (httpx.HTTPError, CircuitBreakerError):
            status = "failed"
        return NotificationLogRecord(
            id=new_id(), request_id=request.id, channel="teams", delivered_at=now() if status == "delivered" else None,
            delivery_status=status,
        )


class SMTPNotificationChannel:
    def __init__(self, smtp_host: str, smtp_port: int, from_addr: str, to_addr: str) -> None:
        self._smtp_host = smtp_host
        self._smtp_port = smtp_port
        self._from_addr = from_addr
        self._to_addr = to_addr

    async def send(self, request: OversightRequestRecord) -> NotificationLogRecord:
        message = EmailMessage()
        message["Subject"] = f"[{request.priority}] New oversight request from {request.requesting_module}"
        message["From"] = self._from_addr
        message["To"] = self._to_addr
        message.set_content(f"Request {request.id} requires review.\n\nContext: {request.context}")
        try:
            with smtplib.SMTP(self._smtp_host, self._smtp_port, timeout=10) as smtp:
                smtp.send_message(message)
            status = "delivered"
        except OSError:
            status = "failed"
        return NotificationLogRecord(
            id=new_id(), request_id=request.id, channel="email", delivered_at=now() if status == "delivered" else None,
            delivery_status=status,
        )


class HTTPDecisionCallbackDispatcher(ResilientHTTPClient):
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(base_url, client=client, timeout=_VERY_SHORT_TIMEOUT, breaker_name="decision-callback")

    async def notify(self, requesting_module: str, requesting_ref: str, decision: DecisionRecord) -> None:
        if requesting_module == "workflow_engine" and ":" in requesting_ref:
            instance_id, approval_id = requesting_ref.split(":", 1)
            await self._post(
                f"/v1/workflow-engine/instances/{instance_id}/approvals/{approval_id}/callback",
                json={"decision": decision.decision.value, "resolved_by": decision.decided_by},
            )
            return

        try:
            await self._post(
                f"/v1/{requesting_module}/oversight-callback",
                json={"requesting_ref": requesting_ref, "decision": decision.decision.value, "decided_by": decision.decided_by},
            )
        except (httpx.HTTPError, CircuitBreakerError) as e:
            logger.warning("oversight_callback_unsupported", requesting_module=requesting_module, error=str(e))


class HTTPAuditabilityClient(ResilientHTTPClient):
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(base_url, client=client, timeout=_VERY_SHORT_TIMEOUT, breaker_name="auditability", fail_max=10)

    async def emit(self, event: dict) -> None:
        try:
            await self._post("/v1/auditability/events", json=event)
        except (httpx.HTTPError, CircuitBreakerError) as exc:
            logger.warning("auditability_emit_failed", error=str(exc))
