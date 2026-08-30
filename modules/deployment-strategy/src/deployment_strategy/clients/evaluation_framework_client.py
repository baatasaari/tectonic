"""HTTP adapter for Evaluation Framework (Module 18) -- one of this
module's two real platform-peer dependencies. Reads that module's own
`GET /scores`, the exact endpoint the Canary Health Calculator's
groundedness signal gates on.

`HTTPEvaluationFrameworkClient` is a `ResilientHTTPClient` (retry +
circuit breaker on every outbound call — see resilience.py) carrying
this platform's service-to-service JWT (`ServiceBearerAuth`), since
Evaluation Framework is a genuine platform peer.
"""
from __future__ import annotations

from typing import Any

import httpx

from deployment_strategy.clients.resilience import ResilientHTTPClient
from deployment_strategy.security.jwt_auth import ServiceBearerAuth

_SHORT_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)

# Evaluation Framework's own list is itself paginated; this client takes a single,
# max-size page as the health check's input rather than walking every page -- a bounded,
# most-recent-first sample is what a gate needs, not a deployment's entire lifetime record.
_SCORE_SAMPLE_LIMIT = 200


class HTTPEvaluationFrameworkClient(ResilientHTTPClient):
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="evaluation-framework", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        super().__init__(base_url, client=client, timeout=_SHORT_TIMEOUT, breaker_name="evaluation-framework", auth=auth)

    async def list_scores(self, *, tenant_id: str, agent_ref: str) -> list[dict[str, Any]]:
        resp = await self._get(
            "/v1/evaluation-framework/scores",
            params={"tenant_id": tenant_id, "agent_ref": agent_ref, "limit": _SCORE_SAMPLE_LIMIT},
        )
        return resp.json().get("items", [])
