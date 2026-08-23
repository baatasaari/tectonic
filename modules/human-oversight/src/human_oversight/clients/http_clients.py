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
"""
from __future__ import annotations

import smtplib
from email.message import EmailMessage

import httpx

from human_oversight.core.domain import (
    DecisionRecord,
    NotificationLogRecord,
    OversightRequestRecord,
    new_id,
    now,
)
from human_oversight.telemetry.logging import get_logger

logger = get_logger(component="http_clients")


class WebhookNotificationChannel:
    def __init__(self, webhook_url: str, client: httpx.AsyncClient | None = None) -> None:
        self._webhook_url = webhook_url
        self._client = client or httpx.AsyncClient(timeout=10.0)

    async def send(self, request: OversightRequestRecord) -> NotificationLogRecord:
        try:
            resp = await self._client.post(self._webhook_url, json={"request_id": request.id, "priority": request.priority})
            resp.raise_for_status()
            status = "delivered"
        except httpx.HTTPError:
            status = "failed"
        return NotificationLogRecord(
            id=new_id(), request_id=request.id, channel="webhook", delivered_at=now() if status == "delivered" else None,
            delivery_status=status,
        )


class SlackNotificationChannel:
    def __init__(self, webhook_url: str, client: httpx.AsyncClient | None = None) -> None:
        self._webhook_url = webhook_url
        self._client = client or httpx.AsyncClient(timeout=10.0)

    async def send(self, request: OversightRequestRecord) -> NotificationLogRecord:
        text = f"New oversight request ({request.priority}) from {request.requesting_module}: {request.id}"
        try:
            resp = await self._client.post(self._webhook_url, json={"text": text})
            resp.raise_for_status()
            status = "delivered"
        except httpx.HTTPError:
            status = "failed"
        return NotificationLogRecord(
            id=new_id(), request_id=request.id, channel="slack", delivered_at=now() if status == "delivered" else None,
            delivery_status=status,
        )


class TeamsNotificationChannel:
    def __init__(self, webhook_url: str, client: httpx.AsyncClient | None = None) -> None:
        self._webhook_url = webhook_url
        self._client = client or httpx.AsyncClient(timeout=10.0)

    async def send(self, request: OversightRequestRecord) -> NotificationLogRecord:
        card = {
            "@type": "MessageCard", "@context": "http://schema.org/extensions",
            "summary": "New oversight request",
            "text": f"New oversight request ({request.priority}) from {request.requesting_module}: {request.id}",
        }
        try:
            resp = await self._client.post(self._webhook_url, json=card)
            resp.raise_for_status()
            status = "delivered"
        except httpx.HTTPError:
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


class HTTPDecisionCallbackDispatcher:
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=10.0)

    async def notify(self, requesting_module: str, requesting_ref: str, decision: DecisionRecord) -> None:
        if requesting_module == "workflow_engine" and ":" in requesting_ref:
            instance_id, approval_id = requesting_ref.split(":", 1)
            resp = await self._client.post(
                f"/v1/workflow-engine/instances/{instance_id}/approvals/{approval_id}/callback",
                json={"decision": decision.decision.value, "resolved_by": decision.decided_by},
            )
            resp.raise_for_status()
            return

        try:
            resp = await self._client.post(
                f"/v1/{requesting_module}/oversight-callback",
                json={"requesting_ref": requesting_ref, "decision": decision.decision.value, "decided_by": decision.decided_by},
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("oversight_callback_unsupported", requesting_module=requesting_module, error=str(e))


class HTTPAuditabilityClient:
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=5.0)

    async def emit(self, event: dict) -> None:
        await self._client.post("/v1/auditability/events", json=event)
