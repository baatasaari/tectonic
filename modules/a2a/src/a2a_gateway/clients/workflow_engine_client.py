"""HTTP adapter for this module's one platform-peer dependency: Workflow
Engine (Module 1), used only to dispatch an accepted inbound task
(`POST /v1/workflow-engine/instances`) — this module's own job stops at
accept/reject/track, per the LLD's "wrap a real peer, don't duplicate
it" convention.

`WorkflowEngineHTTPClient` is a `ResilientHTTPClient` (retry + circuit
breaker on every outbound call — see resilience.py), and — unlike
`clients/a2a_peer_client.py`'s arbitrary external targets — carries this
platform's own service-to-service JWT (`ServiceBearerAuth`), since
Workflow Engine is a genuine platform peer, not a third party.
"""
from __future__ import annotations

from typing import Any

import httpx

from a2a_gateway.clients.resilience import ResilientHTTPClient
from a2a_gateway.security.jwt_auth import ServiceBearerAuth

_SHORT_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)


class WorkflowEngineHTTPClient(ResilientHTTPClient):
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="workflow-engine", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        super().__init__(base_url, client=client, timeout=_SHORT_TIMEOUT, breaker_name="workflow-engine", auth=auth)

    async def start_instance(self, *, definition_id: str, tenant_id: str, initial_context: dict[str, Any]) -> dict[str, Any]:
        resp = await self._post(
            "/v1/workflow-engine/instances",
            json={"definition_id": definition_id, "initial_context": initial_context},
            headers={"X-Tenant-Id": tenant_id},
        )
        return resp.json()
