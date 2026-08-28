# Short-Term Memory — Module 12

Owns the working memory for a single active session: the recent message
buffer that the Conversational Engine and Context Engineering draw on
when assembling a prompt. Distinct from Long-Term Memory, which persists
across sessions; this module's data is scoped to one session's lifetime
and is intentionally lightweight. Full design doc:
[`../../docs/module-12-short-term-memory.md`](../../docs/module-12-short-term-memory.md).

## Layout

```
src/short_term_memory/
  main.py                 FastAPI app, lifespan wiring, /healthz, /metrics
  app_context.py           Process-wide dependency container
  config.py                 Pydantic Settings — LLD config schema
  core/
    domain.py                MessageRecord/BufferState/AppendResult dataclasses
    ports.py                   BufferStore, LLM Gateway summarisation client
    fakes.py                    In-memory implementations of every port, for unit tests
    salience_scorer.py            Salience Scorer — numbers/commitments/"remember this"/entity density
    tokenization.py                 Local token-count estimator
    buffer_manager.py                Buffer Manager — append, overflow detection, summarisation trigger
  clients/                 Redis adapter (literal LLD key patterns) + LLM Gateway HTTP client
  security/                 Service-to-service JWT bearer auth (shared signing key), the entitlement gate, real OpenAPI security scheme declarations
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI router — sessions/{id}/messages, sessions/{id}
  schemas/                    Pydantic request/response models
```

No `db/` or `alembic/` here: the LLD's own data model section is "Redis
structures, not relational," and `clients/redis_buffer_store.py`
implements its three key patterns
(`stm:session:{id}:messages`/`:summary`/`:token_count`) literally.

## Design notes vs. the LLD

- **Resiliency.** Every outbound HTTP call this module makes to a peer module goes through `ResilientHTTPClient` (`clients/resilience.py`): exponential-backoff retry on network errors and 5xx responses (never 4xx — a client error means the peer already processed the request and rejected it, so retrying just repeats the mistake), and a circuit breaker (`aiobreaker`) that opens after repeated failures so a struggling peer gets a break instead of a retry storm, and this module fails fast instead of piling up requests against a peer that's already down.

- **Salience scoring.** The LLD calls for "a lightweight rule-based
  scorer...with an optional LLM-based scorer for higher-value tenants."
  `core/salience_scorer.py` implements the rule-based tier in full
  (numeric content, named-commitment phrases, explicit "remember this"
  cues, and a capitalised-word entity-density proxy). The optional
  LLM-based tier is a `scoring_method: "llm_based"` config value with no
  implementation behind it yet — it's additive to the rule-based path
  the LLD frames as the common case, not a replacement, so it's left as
  a documented gap rather than a deviation requiring a stand-in.
- **Service-to-service JWT auth.** Before this, no module authenticated
  any of its inbound HTTP calls — any process able to reach a module's
  port could call it, and every outbound call this module makes carried
  no credential at all. `security/jwt_auth.py` adds shared-signing-key
  (HS256) bearer auth: `ServiceAuthMiddleware` verifies every inbound
  request's `Authorization: Bearer <JWT>` against this module's own
  `service_name` as the required audience (except `/healthz` and
  `/metrics` — Kubernetes probes and Prometheus scraping carry no auth
  token); `ServiceBearerAuth` (an `httpx.Auth` flow) mints a fresh,
  short-lived (5 min default) token scoped via the `aud` claim to the
  *specific* peer being called on every outbound request this module's
  `HTTPLLMGatewayClient` makes (audience `llm-gateway`) — a token minted
  to call one peer is rejected if replayed against a different one. The
  shared secret (`TECTONIC_JWT_SHARED_SECRET`, one Kubernetes Secret
  referenced by every module's Helm chart under this same literal env
  var name, not a per-module-prefixed one) defaults to an
  obviously-insecure placeholder for zero-config local dev/tests;
  `main.py` logs a startup warning if it's still active. This is
  service-to-service auth for inter-module calls, not the platform's
  external-facing user-auth story — a real API gateway/OAuth layer in
  front of the platform's own entry points is a separate, larger
  concern, out of scope here.

- **Enforces its own subscription entitlement via `EntitlementGateMiddleware`**
  (`security/entitlement_gate.py`) — see Agent Cards' README and the rollout
  playbook doc (`docs/entitlement-gate-rollout.md`) for the shared reference
  implementation. Layered after `ServiceAuthMiddleware` (authenticate, then
  entitle), it calls Multi-tenancy's real `GET /tenants/{id}/gate?module=short-term-memory`,
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

## Running locally

```bash
uv venv && uv pip install -e ".[dev]"
pytest                                                    # unit tests, no external services needed

docker compose -f deploy/docker-compose.yml up --build    # full stack incl. Redis, dependency-stub
```
