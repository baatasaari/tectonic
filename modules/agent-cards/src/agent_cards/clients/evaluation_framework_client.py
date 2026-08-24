"""HTTP adapter for Evaluation Framework (Module 18) -- the performance
half of the Trust Score Calculator's two real-peer signals. Reads that
module's own `GET /scores` endpoint, the same metric-score history it
already computes for its own reasons; this client adds no new scoring
logic of its own.

`HTTPEvaluationFrameworkClient` is a `ResilientHTTPClient` (retry +
circuit breaker on every outbound call — see resilience.py) carrying
this platform's service-to-service JWT (`ServiceBearerAuth`), since
Evaluation Framework is a genuine platform peer.
"""
from __future__ import annotations

from typing import Any

import httpx

from agent_cards.clients.resilience import ResilientHTTPClient
from agent_cards.security.jwt_auth import ServiceBearerAuth

_SHORT_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)

# Evaluation Framework's own list is itself paginated (LLD-standard limit/offset); this
# client takes a single, max-size page as the input to trust scoring rather than walking
# every page -- a bounded, most-recent-first sample of an agent's evaluation history is
# what a trust signal needs, not its entire lifetime record. A documented scoping choice,
# not an oversight.
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
