# Tool Orchestration — Module 4

The single point through which every agent action against an external tool
passes: discovery, invocation, retries, reliability scoring and (for
narrow, well-specified gaps) guarded synthesis of new tools from existing
primitives. Agents never call a third-party API directly. Full design doc:
[`../../docs/module-04-tool-orchestration.md`](../../docs/module-04-tool-orchestration.md).

## Layout

```
src/tool_orchestration/
  main.py                 FastAPI app, lifespan wiring, /healthz, /metrics
  app_context.py           Process-wide dependency container
  config.py                 Pydantic Settings — LLD config schema
  core/
    domain.py                ToolDefinition/ToolInvocation/ReliabilityScore/CircuitBreakerState dataclasses
    ports.py                   Repository, circuit breaker store, MCP adapter, synthesis dependencies
    fakes.py                    In-memory implementations of every port, for unit tests
    circuit_breaker.py           Circuit Breaker — pure state-transition logic
    reliability_scorer.py         Reliability Scorer — EMA-based rolling success rate
    retry_manager.py               Retry Manager — per-tool backoff policy
    tool_synthesis.py               Tool Synthesis Engine — guarded, never self-activates
    orchestration_service.py         The invocation orchestrator (this module's "scheduler")
  db/                      SQLAlchemy 2.0 async models + repository (ToolDefinition/Invocation/ReliabilityScore)
  clients/                 Redis circuit breaker store, MCP HTTP adapter, LLM Gateway/Guardrails/Sentinel clients
  security/                 Service-to-service JWT bearer auth (shared signing key)
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI routers — discovery, invoke, synthesise, approve
  schemas/                    Pydantic request/response models
```

## Design notes vs. the LLD

- **MCP protocol.** The LLD names the official `mcp` Python SDK. `clients/
  mcp_http_client.py` implements `MCPClientAdapter` as a generic
  JSON-RPC-2.0-over-HTTP client instead — JSON-RPC is MCP's wire-level
  shape regardless of transport variant. Swapping in the real SDK (stdio/
  SSE/streamable-HTTP transports, capability negotiation) means
  implementing the same Protocol against it, without touching the circuit
  breaker, retry manager or reliability scorer that drive it — same
  boundary Module 1 draws around ADK and Module 3 draws around LiteLLM.
- **Circuit breaker state is Redis-only.** Per the LLD's stack table, it's
  never persisted to Postgres — losing it just means every tool starts
  "closed" again, which is the safe direction to fail in.
- **Reliability scoring.** Uses an exponential moving average rather than a
  stored rolling-window history, so "real-time update on each invocation"
  (LLD component table) doesn't require accumulating a history buffer per
  tool.
- **Synthesis safety.** `ToolSynthesisEngine` never sets a tool's status to
  `active` — only `POST /tools/{id}/approve` does, and
  `synthesis.require_sentinel_approval` cannot be disabled while synthesis
  is enabled (enforced at config load, not just documented). A synthesised
  tool always passes through Guardrails and gets a Sentinel Agents review
  ticket before it can ever be approved.
- **Service-to-service JWT auth.** Before this, no module authenticated
  any of its inbound HTTP calls — any process able to reach a module's
  port could call it, and every outbound call this module makes to a
  platform peer carried no credential at all. `security/jwt_auth.py` adds
  shared-signing-key (HS256) bearer auth: `ServiceAuthMiddleware` verifies
  every inbound request's `Authorization: Bearer <JWT>` against this
  module's own `service_name` as the required audience (except
  `/healthz` and `/metrics` — Kubernetes probes and Prometheus scraping
  carry no auth token); `ServiceBearerAuth` (an `httpx.Auth` flow) mints a
  fresh, short-lived (5 min default) token scoped via the `aud` claim to
  the *specific* peer being called on every outbound request this
  module's three dependency HTTP clients (`HTTPLLMGatewayClient`,
  `HTTPGuardrailsClient`, `HTTPSentinelAgentsClient`) make — a token
  minted to call one peer is rejected if replayed against a different
  one. `HTTPMCPClientAdapter` is deliberately excluded: it calls
  arbitrary third-party MCP tool servers, not a platform peer, and those
  servers carry their own (or no) auth scheme entirely outside this
  platform's shared-secret trust boundary. The shared secret
  (`TECTONIC_JWT_SHARED_SECRET`, one Kubernetes Secret referenced by
  every module's Helm chart under this same literal env var name, not a
  per-module-prefixed one) defaults to an obviously-insecure placeholder
  for zero-config local dev/tests; `main.py` logs a startup warning if
  it's still active. This is service-to-service auth for inter-module
  calls, not the platform's external-facing user-auth story — a real API
  gateway/OAuth layer in front of the platform's own entry points is a
  separate, larger concern, out of scope here.

## Running locally

```bash
uv venv && uv pip install -e ".[dev]"
pytest                                                    # unit tests, no external services needed

docker compose -f deploy/docker-compose.yml up --build    # full stack incl. Postgres, Redis, dependency-stub
```
