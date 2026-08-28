# Conversational Engine — Module 2

Owns the dialogue layer: turn management, streaming response delivery,
persona/tone enforcement, channel adaptation, and the decision of when to
hand off to a human or another agent. Delegates generation to LLM Gateway,
moderation to Guardrails, escalation to Human Oversight — this module
orchestrates those calls within a conversation, it does not duplicate their
logic. Full design doc: [`../../docs/module-02-conversational-engine.md`](../../docs/module-02-conversational-engine.md).

## Layout

Mirrors Module 1's package shape:

```
src/conversational_engine/
  main.py                 FastAPI app, lifespan wiring, /healthz, /metrics
  app_context.py           Process-wide dependency container
  config.py                 Pydantic Settings — LLD config schema
  core/
    domain.py                Session/Message/HandoffEvent/PersonaConfig dataclasses
    ports.py                  Repository, hot state store, and the module's 4 external clients
    fakes.py                   In-memory implementations of every port, for unit tests
    emotion.py                  Emotion/Urgency Detector — heuristic scorer with optional LLM refinement
    persona.py                   Persona Engine — prompt building + denied-topic short-circuit
    refusal.py                    Explainable Refusal Composer
    handoff.py                     Handoff Trigger Engine — deterministic escalation rules
    session_manager.py              The turn orchestrator (this module's "scheduler")
  db/                      SQLAlchemy 2.0 async models + repository (durable history)
  clients/                 Redis hot-state store, HTTP clients for the 4 external modules
  security/                 Service-to-service JWT bearer auth (shared signing key), the entitlement gate, real OpenAPI security scheme declarations
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI routers — sessions, turn (SSE or JSON), handoff, close
  schemas/                    Pydantic request/response models
```

## Design notes vs. the LLD

- **Resiliency.** Every outbound HTTP call this module makes to a peer module goes through `ResilientHTTPClient` (`clients/resilience.py`): exponential-backoff retry on network errors and 5xx responses (never 4xx — a client error means the peer already processed the request and rejected it, so retrying just repeats the mistake), and a circuit breaker (`aiobreaker`) that opens after repeated failures so a struggling peer gets a break instead of a retry storm, and this module fails fast instead of piling up requests against a peer that's already down.

- **Streaming.** `SessionManager.handle_turn` takes an optional `on_chunk`
  callback so the same turn-processing path serves both the SSE endpoint
  (`POST /sessions/{id}/messages?stream=true`) and a plain JSON response —
  no duplicated orchestration logic between the two.
- **Emotion/Urgency Detector.** The LLD calls for "a lightweight classifier
  ... not a separate heavyweight service." `core/emotion.py` implements a
  zero-latency heuristic scorer (frustration/urgency keyword markers,
  punctuation intensity, caps ratio) and only calls out to LLM Gateway's
  classification endpoint when that heuristic lands in an uncertain middle
  band — refinement, not a hard dependency on every turn.
- **Explainable refusal.** Both the Persona Engine's denied-topic check and
  a Guardrails block route through the same `RefusalComposer`, so every
  refusal — pre- or post-generation — carries a `violation_category`
  traceable to a specific rule.
- **Session state tiers.** Redis (`SessionStateStore`) holds only the
  per-session turn counters the Handoff Trigger Engine needs (e.g.
  consecutive refusals); Postgres holds the durable session/message/handoff
  history. Losing Redis loses escalation memory, not conversation history.
- **Postgres integration tests** — the repository layer is now also tested
  against a real Postgres (`tests/integration/`, opt-in via
  `TECTONIC_TEST_POSTGRES_URL` or Docker+testcontainers), covering nested
  `guardrail_check_result` / `tone_settings` / topic-list JSONB round-tripping
  and real UUID primary keys that SQLite's unit-tier fakes can't reliably
  prove. See `tests/integration/conftest.py` for how the Postgres instance is
  obtained. This tier's presence prompted a platform-wide sweep of every
  module's `db/models.py` for the same class of bug: `Mapped[datetime]`
  columns missing `DateTime(timezone=True)` despite the Alembic migration
  already defining them as timestamptz and the domain layer's defaults being
  tz-aware — invisible under SQLite, but a real correctness bug against
  Postgres once a domain default (or an explicit value) is written. Found and
  fixed here too.

- **Connection pooling tuned to replica count.** SQLAlchemy's out-of-
  the-box defaults (`pool_size=5`, `max_overflow=10`) are the same
  regardless of how many pods are running — at this module's own
  `deploy/helm/conversational-engine/values.yaml` `autoscaling.maxReplicas: 20`,
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
  six HTTP clients (`HTTPLLMGatewayClient`, `HTTPGuardrailsClient`,
  `HTTPLongTermMemoryClient`, `HTTPHumanOversightClient`,
  `HTTPObservabilityClient`, `HTTPAuditabilityClient` — the last targets
  Module 20, Auditability) make — a token minted to
  call one peer is rejected if replayed against a different one. The
  shared secret (`TECTONIC_JWT_SHARED_SECRET`, one Kubernetes Secret
  referenced by every module's Helm chart under this same literal env
  var name, not a per-module-prefixed one) defaults to an obviously-
  insecure placeholder for zero-config local dev/tests; `main.py` logs a
  startup warning if it's still active. This is service-to-service auth
  for inter-module calls, not the platform's external-facing user-auth
  story — a real API gateway/OAuth layer in front of the platform's own
  entry points is a separate, larger concern, out of scope here.

- **Enforces its own subscription entitlement via `EntitlementGateMiddleware`**
  (`security/entitlement_gate.py`) — see Agent Cards' README and the rollout
  playbook doc (`docs/entitlement-gate-rollout.md`) for the shared reference
  implementation. Layered after `ServiceAuthMiddleware` (authenticate, then
  entitle), it calls Multi-tenancy's real `GET /tenants/{id}/gate?module=conversational-engine`,
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

## Running locally

```bash
uv venv && uv pip install -e ".[dev]"
pytest                                                    # unit tests, no external services needed

docker compose -f deploy/docker-compose.yml up --build    # full stack incl. Postgres, Redis, dependency-stub
```
