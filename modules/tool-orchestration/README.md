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
  security/                 Service-to-service JWT bearer auth (shared signing key), the entitlement gate, real OpenAPI security scheme declarations
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI routers — discovery, invoke, synthesise, approve
  schemas/                    Pydantic request/response models
```

## Design notes vs. the LLD

- **Resiliency.** Every outbound HTTP call this module makes to a peer module goes through `ResilientHTTPClient` (`clients/resilience.py`): exponential-backoff retry on network errors and 5xx responses (never 4xx — a client error means the peer already processed the request and rejected it, so retrying just repeats the mistake), and a circuit breaker (`aiobreaker`) that opens after repeated failures so a struggling peer gets a break instead of a retry storm, and this module fails fast instead of piling up requests against a peer that's already down.

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
- **Postgres integration tests** — the repository layer is now also tested
  against a real Postgres (`tests/integration/`, opt-in via
  `TECTONIC_TEST_POSTGRES_URL` or Docker+testcontainers), covering the
  `ToolDefinition.schema` JSONB round trip, a real UUID primary key, a
  multi-row `list_tool_definitions` query filtered by tenant and status, and
  an upsert-style reliability-score update that must touch only the targeted
  tool's row — all things SQLite's unit-tier fakes can't reliably prove. See
  `tests/integration/conftest.py` for how the Postgres instance is obtained.
  This tier's presence prompted a platform-wide sweep of every module's
  `db/models.py` for the same class of bug: `Mapped[datetime]` columns missing
  `DateTime(timezone=True)` despite the Alembic migration already defining
  them as timestamptz and the domain layer's defaults being tz-aware —
  invisible under SQLite, but a real correctness bug against Postgres once a
  domain default (or an explicit value) is written. Found and fixed here too.

- **`GET /tools` pagination.** Added `limit`/`offset` query params
  (default `limit=50`, max `200`); the response shape changed from a
  bare array to `ToolDefinitionListResponse`
  (`items`/`total`/`limit`/`offset`). `ToolRepository.list_tool_definitions`
  now returns `(items, total)`. No existing deterministic order — added
  `ORDER BY created_at ASC, id ASC` (registration order, with `id` as a
  tiebreaker) so limit/offset pagination is stable.

- **Connection pooling tuned to replica count.** SQLAlchemy's out-of-
  the-box defaults (`pool_size=5`, `max_overflow=10`) are the same
  regardless of how many pods are running — at this module's own
  `deploy/helm/tool-orchestration/values.yaml` `autoscaling.maxReplicas: 20`,
  that's up to 300 connections to this module's own Postgres
  instance from this module alone at full autoscale, with no one having
  deliberately decided that number. `db/session.py`'s `make_engine` now
  passes explicit, configurable `pool_size=5` /
  `max_overflow=2` (`db_pool_size`/`db_max_overflow`
  Settings, env-overridable) sized so this module's own steady-state
  total stays at ~100 connections and its full-burst total at ~150,
  even at `maxReplicas`. `pool_recycle=1800s` also avoids stale
  connections behind a cloud LB/proxy's own idle-connection timeout —
  a real, independent gap, not just a replica-count one.
- **Pagination on `GET /tools`.** Added `limit`/`offset` query params
  (default 50, max 200) and a `ToolDefinitionListResponse` envelope
  (`items`/`total`/`limit`/`offset`) — this endpoint previously returned
  every registered tool for a tenant unbounded. Ordered by `created_at`
  ascending (registration order) with `id` as a tiebreaker for a stable
  page boundary.

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

- **Enforces its own subscription entitlement via `EntitlementGateMiddleware`**
  (`security/entitlement_gate.py`) — see Agent Cards' README and the rollout
  playbook doc (`docs/entitlement-gate-rollout.md`) for the shared reference
  implementation. Layered after `ServiceAuthMiddleware` (authenticate, then
  entitle), it calls Multi-tenancy's real `GET /tenants/{id}/gate?module=tool-orchestration`,
  denying with `402 Payment Required` when the tenant's subscription doesn't
  include this module. It **fails open** if Multi-tenancy is unreachable — a
  deliberate contrast with `ServiceAuthMiddleware`'s zero-trust fail-closed
  posture.

- **Its generated OpenAPI document declares the real auth it enforces**
  (`security/openapi_security.py`) — see Workflow Engine's README and the
  independent architecture assessment's §3.6 for the shared reference
  implementation and full reasoning. `ServiceAuthMiddleware` is plain
  Starlette middleware, invisible to FastAPI's automatic OpenAPI
  generation, so this module's spec previously declared no
  `securitySchemes` at all; `configure_openapi_security` fixes that,
  reusing `jwt_auth.py`'s own `_EXCLUDED_PATHS` as the one source of
  truth for which paths are genuinely unauthenticated.

- **Kubernetes hardening** (`deploy/helm/`; independent architecture
  assessment §3.7) — see Workflow Engine's README for the full reasoning
  and reference implementation. A dedicated ServiceAccount with no
  auto-mounted API token (this module never calls the Kubernetes API);
  pod/container `securityContext` (non-root, read-only root filesystem
  with a small `/tmp` `emptyDir`, all capabilities dropped, a seccomp
  profile); a `NetworkPolicy` restricting ingress to this module's own
  namespace; separate startup/liveness/readiness probe semantics instead
  of two identical probes; and `topologySpreadConstraints` across nodes.

- **Plain registration for a known, already-specified tool** (ticket #82)
  — the only creation path before this (`/synthesise` → `/approve`)
  always calls LLM Gateway to invent a tool proposal and always requires
  a Sentinel Agents review, right for an LLM-invented tool but wrong for
  an admin-known integration (this slice's own `get_order_status`, a
  real merchant order-status backend nobody needs an LLM to guess the
  schema of). Added `POST /tools`, registering directly as
  `active`/`synthesised=False`.

- **NUL bytes in a raw string query parameter reaching the database
  unvalidated** (ticket #82's platform-wide sweep, following the same bug
  a real CI run found on Multi-tenancy's and Billing and Metering's own
  contract tiers — see either module's own README for the original
  finding; this module wasn't in that sweep's original module list —
  found by re-grepping the whole platform for the same pattern once the
  sweep was otherwise done). `GET /tools`'s `status` never ran through
  a NUL-byte validator — a plain, un-wrapped `str` function parameter
  rather than an explicit `Query()` default, which is why the earlier
  grep for `Query(` missed this file; fixed with
  `_reject_null_byte_query()`. No route-level test file existed for
  this module before this fix — `tests/unit/test_routes_tools.py`
  (new) pins just this regression; comprehensive route coverage
  remains a real, separately-scoped gap.

## Running locally

```bash
uv venv && uv pip install -e ".[dev]"
pytest                                                    # unit tests, no external services needed

docker compose -f deploy/docker-compose.yml up --build    # full stack incl. Postgres, Redis, dependency-stub
```
