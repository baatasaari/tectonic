"""HTTP adapters for the four external module dependencies this module talks
to at runtime: LLM Gateway, Tool Orchestration, Guardrails, Human Oversight.

Each of those modules is out of scope for this build (they are their own
platform modules); these clients let Workflow Engine run for real once they
exist, and point at the lightweight dependency-stub service
(../../stubs/dependency-stub) in the meantime — see deploy docker-compose.yml.
Base URLs are plain config, one per dependency, so each can point at a real
module instance or the stub independently.

Every client below is a `ResilientHTTPClient` (retry + circuit breaker on
every outbound call — see resilience.py).
"""
from __future__ import annotations

import json
from typing import Any

import httpx

from workflow_engine.clients.resilience import ResilientHTTPClient
from workflow_engine.security.jwt_auth import ServiceBearerAuth

_SHORT_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)

# One shared virtual key for every completion this module makes, deployment-
# configured (WorkflowEngineSettings.llm_gateway_virtual_key) rather than
# resolved per-tenant/per-step — real per-tenant virtual key resolution
# (looking one up via Multi-tenancy or a tenant->key mapping) is real,
# separately-scoped follow-up work, not this ticket's own client-adapter fix.
_DEFAULT_VIRTUAL_KEY = "workflow-engine-default"


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

    async def complete(
        self, *, agent_ref: str, prompt_context: dict[str, Any], tenant_id: str, trace_id: str
    ) -> tuple[dict[str, Any], float]:
        # A genuine module-level gap ticket #82 surfaced standing this module up
        # against a real running LLM Gateway for the first time: this client was
        # never actually validated against LLM Gateway's real API -- it posted an
        # invented `/v1/completions {agent_ref, context, tenant_id}` shape (with a
        # `confidence_score` in the response) that LLM Gateway's real routes never
        # implemented (its real surface is the OpenAI-compatible
        # `/v1/llm-gateway/chat/completions`, needing `X-Virtual-Key`/`X-Tenant-Id`
        # headers and a `messages` list, LLD §3.3) — invisible before because every
        # prior test/run stubbed this call. `prompt_context` (the accumulated
        # per-step instance context, keyed by step_id, not a chat history) is
        # JSON-serialized as one user message; a mock/real model behind LLM
        # Gateway's own ProviderConfig is expected to introspect that JSON rather
        # than read natural prose, which is exactly what this slice's own mock
        # provider stub does (see docs/phase2-product-slice-01-support-agent.md).
        #
        # LLM Gateway's real chat-completion response carries no confidence score
        # (a genuinely separate, not-yet-designed accounting question — see its own
        # README's `tokens_per_minute` note for the same class of deferred gap) --
        # this slice's own escalation path is a business-rule threshold on the
        # refund amount, not confidence-gated, so a fixed default here drives no
        # real decision in this slice; a future slice that needs genuine
        # confidence-gated escalation on a real LLM Gateway call needs LLM Gateway
        # to expose one first.
        resp = await self._post(
            "/v1/llm-gateway/chat/completions",
            json={
                "model": agent_ref,
                "messages": [{"role": "user", "content": json.dumps(prompt_context, default=str)}],
                "routing_hints": {"task_type": "chat"},
            },
            headers={"X-Trace-Id": trace_id, "X-Virtual-Key": self._default_virtual_key, "X-Tenant-Id": tenant_id},
        )
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        # A step that needs to act on structured fields (`tool_arguments` for
        # a tool-calling step, e.g.) needs them as real top-level keys of the
        # returned response dict, not buried inside a JSON-encoded string --
        # a provider/mock behind LLM Gateway that wants to communicate more
        # than plain prose back can return a JSON object (with its own
        # "content" key) as its message content; this unwraps it losslessly.
        # Plain prose (the common, final-answer case) falls through as-is.
        try:
            parsed = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            parsed = None
        if isinstance(parsed, dict) and "content" in parsed:
            return parsed, 0.95
        return {"content": content}, 0.95


class HTTPToolOrchestrationClient(ResilientHTTPClient):
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="tool-orchestration", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        super().__init__(base_url, client=client, breaker_name="tool-orchestration", auth=auth)

    async def invoke(
        self, *, tool_ref: str, arguments: dict[str, Any], agent_ref: str, tenant_id: str, trace_id: str
    ) -> dict[str, Any]:
        # Another real wire-shape mismatch ticket #82 surfaced (same class as
        # LLM Gateway's and Human Oversight's own clients above): this posted
        # an invented `/v1/tools/invoke {tool_ref, arguments, tenant_id}`
        # shape. Tool Orchestration's real route is
        # `/v1/tool-orchestration/invoke`, needing `InvokeToolRequest`'s real
        # fields (`tool_id`, `parameters`, `agent_ref`, `workflow_instance_id`)
        # and an `X-Tenant-Id` header, not a tenant_id body field.
        # `tool_ref` here is expected to already be Tool Orchestration's own
        # real `tool_id` (a workflow definition's own `config.tool_refs`
        # embeds the concrete id after registering the tool -- see
        # docs/phase2-product-slice-01-support-agent.md).
        resp = await self._post(
            "/v1/tool-orchestration/invoke",
            json={"tool_id": tool_ref, "parameters": arguments, "agent_ref": agent_ref},
            headers={"X-Trace-Id": trace_id, "X-Tenant-Id": tenant_id},
        )
        return resp.json()


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
        # Another real wire-shape mismatch ticket #82 surfaced (same class as
        # LLM Gateway's/Human Oversight's/Tool Orchestration's own clients
        # above): this posted an invented `{content, policy_profile,
        # tenant_id}` body and read an invented `{allowed, detail}` response.
        # Guardrails' real CheckRequest needs `text` (a string) + `stage`
        # ("input"/"output") + an X-Tenant-Id header (not a body field); its
        # real CheckResponse carries `decision` ("allow"/"block"/"redact"),
        # not `allowed`. `policy_profile` (this port's own generic string) is
        # deliberately not translated to `policy_profile_id` -- Guardrails
        # already falls back to a real auto-created default profile per
        # tenant when none is given (see its own `_default_profile`), which is
        # the common case every existing caller of this port actually wants.
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


class HTTPAgenticRAGClient(ResilientHTTPClient):
    """Adapter to Agentic RAG (Module 6) — added for the retrieve step
    (ticket #82); this module had no client for Agentic RAG before."""

    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="agentic-rag", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        super().__init__(base_url, client=client, breaker_name="agentic-rag", auth=auth)

    async def retrieve(self, *, query: str, tenant_id: str) -> dict[str, Any]:
        resp = await self._post(
            "/v1/agentic-rag/retrieve",
            json={"query": query},
            headers={"X-Tenant-Id": tenant_id},
        )
        return resp.json()


class HTTPIntentDetectionClient(ResilientHTTPClient):
    """Adapter to Intent Detection (Module 5) — added for the intent step
    (ticket #82); this module had no client for Intent Detection before."""

    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="intent-detection", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        super().__init__(base_url, client=client, timeout=_SHORT_TIMEOUT, breaker_name="intent-detection", auth=auth)

    async def classify(self, *, message: str, tenant_id: str) -> tuple[str, float]:
        resp = await self._post(
            "/v1/intent-detection/classify",
            json={"text": message},
            headers={"X-Tenant-Id": tenant_id},
        )
        data = resp.json()
        intents = data.get("intents") or []
        if not intents:
            return "unknown", 0.0
        top = intents[0]
        return top["name"], float(top["confidence"])


class HTTPHumanOversightClient(ResilientHTTPClient):
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="human-oversight", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        super().__init__(base_url, client=client, timeout=_SHORT_TIMEOUT, breaker_name="human-oversight", auth=auth)

    async def request_approval(
        self, *, approval_request_id: str, step_execution_id: str, instance_id: str,
        context: dict[str, Any], tenant_id: str,
    ) -> str:
        # A genuine module-level gap ticket #82 surfaced standing this module up
        # against a real running Human Oversight for the first time: this client
        # posted an invented `/v1/oversight/requests` path (Human Oversight's real
        # router is mounted at `/v1/human-oversight`) with an invented body shape
        # and read a `human_oversight_ref_id` response field that Human Oversight's
        # real `CreateRequestRequest`/`OversightRequestSchema` never had (`id`) --
        # invisible before because every prior test/run stubbed this call.
        # `requesting_module`/`requesting_ref` follow the exact contract Human
        # Oversight's own real decision-callback dispatcher already documents
        # (clients/http_clients.py there) for resuming a workflow-engine-originated
        # request: `requesting_ref="{instance_id}:{approval_request_id}"`.
        resp = await self._post(
            "/v1/human-oversight/requests",
            json={
                "tenant_id": tenant_id,
                "requesting_module": "workflow_engine",
                "requesting_ref": f"{instance_id}:{approval_request_id}",
                "context": context,
            },
        )
        return resp.json()["id"]
