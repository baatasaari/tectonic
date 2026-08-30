"""HTTP adapters for this module's external dependencies: LLM Gateway,
Guardrails, Long-Term Memory, Human Oversight, Observability, Auditability.
Each has its own distinct `<peer>_base_url` config field (config.py) — point
each one at its real peer's base URL in any environment running both;
`deploy/docker-compose.yml` points all of them at one dependency-stub
service for standalone dev/test instead.

Every client below is a `ResilientHTTPClient` (retry + circuit breaker on
every outbound call — see resilience.py) except `stream_complete`, which is
deliberately left unwrapped: retrying a partially-consumed SSE stream is
unsafe, so a streaming caller needs its own reconnect story if it wants one.

**Real wire shapes, not invented ones (Phase 2 assessment follow-up).** Every
client below used to post an invented path/body and parse an invented
response shape — exactly the class of bug ticket #82 found and fixed
platform-wide in every OTHER module's peer clients, but never in this
module's own DIRECT (non-`workflow_routing`) turn-handling path, because the
Phase 2 product-slice test exercised only the `workflow_routing.enabled`
path. Standing this module's own direct path up against real running peers
for the first time (per the independent architecture assessment's own
Phase 2 exit bar) surfaced the same bug in every client here except
`HTTPWorkflowEngineClient` (already fixed in #82) and `HTTPAuditabilityClient`
(already correct — Auditability's real `POST /v1/auditability/events`
accepts any `dict` body with a `tenant_id` key, so the pre-existing call
already worked). Fixed against each peer's own real route/schema below,
each with its own comment explaining what was wrong and why.
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import httpx

from conversational_engine.clients.resilience import CircuitBreakerError, ResilientHTTPClient
from conversational_engine.security.jwt_auth import ServiceBearerAuth
from conversational_engine.telemetry.logging import get_logger

logger = get_logger(component="http_clients")

_SHORT_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)
_VERY_SHORT_TIMEOUT = httpx.Timeout(connect=5.0, read=5.0, write=5.0, pool=5.0)

# One shared virtual key for every completion this module makes, deployment-
# configured (ConversationalEngineSettings.llm_gateway_virtual_key) rather
# than resolved per-tenant/per-persona -- real per-tenant virtual key
# resolution is real, separately-scoped follow-up work, the same documented
# simplification Workflow Engine's own HTTPLLMGatewayClient already
# established (ticket #82) for the identical problem.
_DEFAULT_VIRTUAL_KEY = "conversational-engine-default"


class HTTPLLMGatewayClient(ResilientHTTPClient):
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
        default_virtual_key: str = _DEFAULT_VIRTUAL_KEY,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="llm-gateway", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        super().__init__(base_url, client=client, breaker_name="llm-gateway", auth=auth)
        self._default_virtual_key = default_virtual_key

    async def stream_complete(
        self, *, prompt_context: dict[str, Any], tenant_id: str, trace_id: str
    ) -> AsyncIterator[str]:
        """Posted an invented `/v1/completions/stream` (LLM Gateway has no
        such route -- and no streaming route at all: its real surface,
        `/v1/llm-gateway/chat/completions`, is single-response, LLD §3.3)
        with an invented `{context, tenant_id}` body, expecting an invented
        `data: {"text": ...}` SSE protocol. Fixed to call the real,
        non-streaming endpoint (`X-Virtual-Key`/`X-Tenant-Id` headers, a
        `messages` list -- the same real shape Workflow Engine's own
        `HTTPLLMGatewayClient.complete` already established, ticket #82) and
        yield its full response as one chunk. This module's own SSE contract
        to ITS OWN callers (`POST .../messages?stream=true`) is unchanged and
        still real -- what's honest is only that the *upstream* hop to LLM
        Gateway is not actually token-by-token yet, since LLM Gateway itself
        has no streaming completions endpoint to relay from. A real
        perceived-streaming improvement needs LLM Gateway to grow one first,
        separately scoped."""
        resp = await self._post(
            "/v1/llm-gateway/chat/completions",
            json={
                "model": prompt_context.get("persona_name", "default"),
                "messages": [{"role": "user", "content": json.dumps(prompt_context, default=str)}],
                "routing_hints": {"task_type": "chat"},
            },
            headers={"X-Trace-Id": trace_id, "X-Virtual-Key": self._default_virtual_key, "X-Tenant-Id": tenant_id},
        )
        data = resp.json()
        yield data["choices"][0]["message"]["content"]

    async def classify(self, *, text: str, taxonomy: list[str], tenant_id: str) -> dict[str, float]:
        """Posted an invented `/v1/classify` -- LLM Gateway has no
        classification endpoint at all, only `/chat/completions` and
        `/embeddings`. This is a refinement signal only (the Emotion/Urgency
        Detector's own heuristic already scores every turn; this only runs
        when that heuristic lands in an uncertain middle band, and its
        caller already treats any failure here as non-fatal, falling back to
        the heuristic score -- see `core/emotion.py`). Fixed to ask the real
        `/chat/completions` endpoint for a JSON classification instead of
        inventing a dedicated endpoint LLM Gateway doesn't have; a
        non-JSON or malformed response degrades to an empty result, which
        the caller already treats the same as "no refinement available"."""
        prompt = (
            f"Classify the emotional tone of this message against exactly these labels: "
            f"{', '.join(taxonomy)}. Respond with ONLY a JSON object mapping each label to a "
            f"confidence score between 0 and 1, e.g. {{\"{taxonomy[0]}\": 0.8}}.\n\nMessage: {text}"
        )
        resp = await self._post(
            "/v1/llm-gateway/chat/completions",
            json={
                "model": "classification",
                "messages": [{"role": "user", "content": prompt}],
                "routing_hints": {"task_type": "classification"},
            },
            headers={"X-Virtual-Key": self._default_virtual_key, "X-Tenant-Id": tenant_id},
        )
        content = resp.json()["choices"][0]["message"]["content"]
        try:
            scores = json.loads(content)
        except json.JSONDecodeError:
            return {}
        if not isinstance(scores, dict):
            return {}
        return {k: float(v) for k, v in scores.items() if isinstance(v, (int, float))}


class HTTPGuardrailsClient(ResilientHTTPClient):
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="guardrails", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        super().__init__(base_url, client=client, timeout=_SHORT_TIMEOUT, breaker_name="guardrails", auth=auth)

    async def check(
        self, *, content: dict[str, Any], policy_profile: str, tenant_id: str
    ) -> tuple[bool, dict[str, Any]]:
        """Posted an invented `{content, policy_profile, tenant_id}` body and
        read an invented `{allowed, detail}` response. Guardrails' real
        `CheckRequest` needs `text` (a string) + `stage` ("input"/"output")
        + an `X-Tenant-Id` header (not a body field); its real
        `CheckResponse` carries `decision` ("allow"/"block"/"redact"), not
        `allowed` -- the same real shape Workflow Engine's own
        `HTTPGuardrailsClient.check` already established for this identical
        port contract (ticket #82). `policy_profile` (this port's own
        generic string) is deliberately not translated to
        `policy_profile_id` -- Guardrails already falls back to a real
        auto-created default profile per tenant when none is given."""
        stage = "output" if "output" in content else "input"
        text = content.get("output") or content.get("input") or content
        if not isinstance(text, str):
            text = json.dumps(text, default=str)
        resp = await self._post(
            "/v1/guardrails/check",
            json={"text": text, "stage": stage},
            headers={"X-Tenant-Id": tenant_id},
        )
        data = resp.json()
        allowed = data["decision"] != "block"
        detail = {"violation_category": data.get("violation_category"), "checks_run": data.get("checks_run", [])}
        return allowed, detail


class HTTPWorkflowEngineClient(ResilientHTTPClient):
    """Adapter to Workflow Engine (Module 1) — added for the Phase 2
    support-agent slice (ticket #82); this module had no client for Workflow
    Engine before this."""

    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="workflow-engine", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        super().__init__(base_url, client=client, breaker_name="workflow-engine", auth=auth)

    async def start_instance(
        self, *, definition_id: str, initial_context: dict[str, Any], tenant_id: str
    ) -> dict[str, Any]:
        resp = await self._post(
            "/v1/workflow-engine/instances",
            json={"definition_id": definition_id, "initial_context": initial_context},
            headers={"X-Tenant-Id": tenant_id},
        )
        started = resp.json()
        # start_instance's own POST runs the graph synchronously but its
        # response (StartInstanceResponse) never echoes back the resulting
        # context -- a second real call to the same real instance fetches it,
        # rather than this module guessing at or duplicating Workflow
        # Engine's own instance-detail shape.
        detail = await self._fetch_instance_detail(started["id"], tenant_id)
        return {
            "id": started["id"], "status": detail["status"], "trace_id": started["trace_id"],
            "context": detail.get("context", {}),
        }

    async def get_instance(self, *, instance_id: str, tenant_id: str) -> dict[str, Any]:
        detail = await self._fetch_instance_detail(instance_id, tenant_id)
        return {
            "id": instance_id, "status": detail["status"], "trace_id": detail.get("trace_id", ""),
            "context": detail.get("context", {}),
        }

    async def _fetch_instance_detail(self, instance_id: str, tenant_id: str) -> dict[str, Any]:
        resp = await self._get(f"/v1/workflow-engine/instances/{instance_id}", headers={"X-Tenant-Id": tenant_id})
        return resp.json()


class HTTPLongTermMemoryClient(ResilientHTTPClient):
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="long-term-memory", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        super().__init__(base_url, client=client, timeout=_SHORT_TIMEOUT, breaker_name="long-term-memory", auth=auth)

    async def recall_identity_context(
        self, *, user_ref: str, tenant_id: str, query: str = "", top_k: int = 5,
    ) -> dict[str, Any] | None:
        """Called an invented `GET /v1/memory/identity` -- Long-Term Memory
        has no such route; its real, and only, retrieval surface is
        `POST /v1/long-term-memory/query` (LLD §3.1), which ranks a tenant's
        active memory items in one `scope` by text/semantic match against a
        `query` string -- there is no "fetch everything in scope" call. This
        module was also never actually calling this client at all before
        (SessionManager never received a `long_term_memory` port instance --
        see session_manager.py); fixed on both ends together. Recall is
        scoped to `user:{user_ref}` by convention (nothing else in this
        platform writes memories under that scope yet -- writing user
        identity facts into Long-Term Memory from a real conversation is
        real, separately-scoped follow-up work: this module's own job is to
        recall, not to author, those memories) and keyed by the CURRENT
        turn's own message text as the query, so what's recalled is what's
        actually relevant to what the user is asking right now, not a blind
        dump -- matching the LLD's own differentiator framing ("recognises a
        returning user... resumes context without re-asking"). Returns
        `None` on a genuinely empty result (nothing recalled), never raises
        for that case -- an empty scope is not a peer failure."""
        resp = await self._post(
            "/v1/long-term-memory/query",
            json={"scope": f"user:{user_ref}", "query": query, "top_k": top_k},
            headers={"X-Tenant-Id": tenant_id},
        )
        items = resp.json()
        if not items:
            return None
        return {
            "items": [
                {"content": ranked["item"]["content"], "memory_type": ranked["item"]["memory_type"], "score": ranked["score"]}
                for ranked in items
            ],
        }


class HTTPHumanOversightClient(ResilientHTTPClient):
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="human-oversight", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        super().__init__(base_url, client=client, timeout=_SHORT_TIMEOUT, breaker_name="human-oversight", auth=auth)

    async def request_handoff(
        self, *, session_id: str, trigger_reason: str, context: dict[str, Any], tenant_id: str
    ) -> str:
        """Posted an invented `/v1/oversight/handoff-request` (Human
        Oversight's real router is mounted at `/v1/human-oversight`) with an
        invented body shape, and read an invented `human_oversight_ref_id`
        response field that its real `OversightRequestSchema` never had
        (`id`) -- the same real shape Workflow Engine's own
        `HTTPHumanOversightClient.request_approval` already established for
        this identical peer (ticket #82). `requesting_ref` is this module's
        own `session_id` -- Human Oversight doesn't need to know it came
        from a conversation turn specifically, only a stable ref this
        module can use to find its own record of the escalation again."""
        resp = await self._post(
            "/v1/human-oversight/requests",
            json={
                "tenant_id": tenant_id,
                "requesting_module": "conversational_engine",
                "requesting_ref": session_id,
                "context": {"trigger_reason": trigger_reason, **context},
            },
        )
        return resp.json()["id"]


class HTTPObservabilityClient(ResilientHTTPClient):
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="observability", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        super().__init__(base_url, client=client, timeout=_VERY_SHORT_TIMEOUT, breaker_name="observability", fail_max=10, auth=auth)

    async def emit(self, event: dict[str, Any]) -> None:
        """Posted an invented `/v1/observability/events` with a raw event
        dict. Observability's real, and only, ingestion surface is
        `POST /v1/observability/ingest`, which takes a `trace_id` plus a
        list of OTel-shaped spans (`SpanInput`), not an arbitrary business
        event -- this module's own conversation-lifecycle events
        (`conversation.turn.completed` etc.) are business events, not trace
        spans, and this platform's real trace pipeline for this module
        already runs independently via OTel auto-instrumentation
        (`configure_tracing`/`FastAPIInstrumentor`/`HTTPXClientInstrumentor`
        in main.py) -- this bespoke push duplicated, and never actually
        reached, that pipeline. Adapted rather than removed: each event
        becomes one real, zero-duration span carrying the full event as its
        `attributes`, so the call succeeds against Observability's real API
        and the event data is still queryable there, without fabricating a
        misleading non-zero duration this module never measured. Best-effort,
        as before this module had retry/breaker wiring: telemetry emission
        must never be the reason a real request fails."""
        try:
            now = datetime.now(UTC).isoformat()
            await self._post(
                "/v1/observability/ingest",
                json={
                    "tenant_id": event.get("tenant_id", ""),
                    "trace_id": event.get("trace_id", ""),
                    "spans": [
                        {
                            "span_id": event.get("session_id", "unknown"),
                            "name": event.get("event_type", "conversation.event"),
                            "service_name": "conversational-engine",
                            "start_time": now,
                            "end_time": now,
                            "attributes": event,
                        }
                    ],
                },
            )
        except (httpx.HTTPError, CircuitBreakerError) as exc:
            logger.warning("observability_emit_failed", error=str(exc))


class HTTPAuditabilityClient(ResilientHTTPClient):
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="auditability", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        super().__init__(base_url, client=client, timeout=_VERY_SHORT_TIMEOUT, breaker_name="auditability", fail_max=10, auth=auth)

    async def emit(self, event: dict[str, Any]) -> None:
        # Already correct against the real peer: Auditability's real
        # `POST /v1/auditability/events` accepts any dict body requiring
        # only `tenant_id` (see its own routes_auditability.py) -- this
        # call needed no fix, unlike its siblings above.
        try:
            await self._post("/v1/auditability/events", json=event)
        except (httpx.HTTPError, CircuitBreakerError) as exc:
            logger.warning("auditability_emit_failed", error=str(exc))
