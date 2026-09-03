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
  api/                       FastAPI routers — sessions (create/get/list/export/delete), turn (SSE or JSON), resume, handoff, close
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
  include this module. This module and Agent Cards are the two reference
  implementations of the **bounded-staleness** version of this middleware
  (`docs/entitlement-gate-rollout.md`'s "Bounded-staleness cache upgrade"):
  a decision verified via a real, successful Multi-tenancy call is still
  served for up to `entitlement_gate_max_staleness_seconds` after
  Multi-tenancy becomes unreachable (each cached decision is HMAC-signed
  against forgery/corruption), but a request with no verified decision
  inside that window now fails **closed** (`402`) rather than the older,
  unconditional fail-open this file used to have — a real Multi-tenancy
  outage can no longer silently and indefinitely disable entitlement
  enforcement. Two Prometheus counters
  (`entitlement_gate_stale_served_total`, `entitlement_gate_fail_closed_total`)
  make both outcomes observable.

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

- **A real Workflow Engine integration** (ticket #82's own Phase 2
  support-agent slice) — `handle_turn()` called LLM Gateway directly for
  every turn before this, never routing through Workflow Engine's own
  neurosymbolic orchestration, contrary to what the slice's own design
  doc's sequence diagram always assumed. Added `WorkflowEngineClient`
  (port + real HTTP adapter + fake) and a new
  `settings.workflow_routing.enabled`-gated path
  (`_handle_turn_via_workflow_engine`) that creates/drives a real
  Workflow Engine instance instead; default off, so every existing
  direct-LLM-Gateway turn is completely unaffected.

- **`resume_from_workflow` — the fix for a real gap this ticket's own
  live verification surfaced**: escalating a turn to Workflow Engine's
  own human-approval pause recorded the escalation and stopped there;
  nothing ever polled the paused instance again once Human Oversight's
  real decision-callback dispatcher resumed it, so an approved refund had
  no way back into the conversation at all (the design doc's own
  Definition of Done item 7: "the reviewer's real decision resumes the
  conversation correctly"). Added `SessionManager.resume_from_workflow()`
  and `POST /v1/conversational-engine/sessions/{id}/resume` — re-checks a
  `HANDED_OFF` session's paused instance and, once it's completed, relays
  the final answer back into the conversation and reactivates the
  session. A no-op call (still paused, or a session never routed through
  Workflow Engine at all) is a `409`, not an error. Needed one small
  repository addition, `get_latest_handoff_event()`.

- **Session list/search/export/delete, and every peer client's real wire
  shape fixed for real** (the independent architecture assessment's Phase 2
  exit bar — "one paid-pilot-ready conversational agent with security,
  evaluation, SLO, cost, and privacy evidence" — picked as the first
  Phase 2 vertical slice to complete after ticket #82's own support-agent
  slice proved the happy path).

  **Session list/search/export/delete** — this module had only
  `GET /{id}`; no way to list, search, export, or delete a session at all.
  Added `GET /sessions` (tenant-scoped, filterable by `status`/`channel`/
  `user_ref`, paginated — `_reject_null_byte_query()` applied per ticket
  #82's own platform-wide sweep, since this is a newly-added route of the
  same shape every other module's own list/search routes already carry
  that guard on), `GET /sessions/{id}/export` (this module's own full
  transcript bundle: session detail + every message + every handoff
  event), and `DELETE /sessions/{id}` (idempotent hard delete, cascading
  to messages/handoff events — no `ON DELETE CASCADE` on those FKs, so the
  repository does the ordered delete explicitly, same pattern this
  platform's other cascading deletes already use). Scoped deliberately to
  this module's own records: a cross-platform privacy erasure (propagating
  to Long-Term Memory, Auditability, etc.) is Long-Term Memory's own
  separately-scoped `POST /erasure-requests` job, not reinvented here.

  **Cross-session identity continuity wired for real.** The LLD's own
  named differentiator ("recognises a returning user... resumes context
  without re-asking, drawing on Long-Term Memory") and its own
  `session.cross_channel_continuity` config flag existed, but
  `SessionManager` never received a `LongTermMemoryClient` port instance
  at all — the client was constructed in `main.py`'s `AppContext` and then
  never passed to `SessionManager`, dead wiring. Fixed: `SessionManager`
  now takes `long_term_memory` and calls it once per turn for a session
  with a `user_ref` (best-effort, fail-open — a Long-Term Memory outage
  must never fail a turn, same posture as every other optional peer call
  here), keyed by the CURRENT message as the query (not a blind
  "everything about this user" dump — see the client's own docstring for
  why), merging the result into `PersonaEngine.build_prompt`'s own
  `identity_context`.

  **Every peer client's real wire shape, fixed for real.** Standing this
  module's own DIRECT turn-handling path (`workflow_routing.enabled=false`,
  the default) up against real running peers for the first time surfaced
  that every client here except `HTTPWorkflowEngineClient` (already fixed
  in #82) and `HTTPAuditabilityClient` (already correct) was posting an
  invented path/body and/or reading an invented response shape — the exact
  same bug class ticket #82 found and fixed platform-wide in every OTHER
  module's peer clients, just never exercised on THIS module's own direct
  path since the ticket #82 product-slice test only ever exercised the
  `workflow_routing` path (which routes through Workflow Engine's own
  already-fixed clients instead). Fixed, each against its peer's real
  route/schema (see `clients/http_clients.py`'s own per-client docstrings
  for the full account):
  - `HTTPLLMGatewayClient.stream_complete` called an invented
    `/v1/completions/stream` — LLM Gateway has no streaming completions
    route at all, only the single-response `/v1/llm-gateway/chat/completions`
    (LLD §3.3). Fixed to call the real endpoint (needing
    `X-Virtual-Key`/`X-Tenant-Id` headers this module previously never
    sent at all — new `llm_gateway_virtual_key` setting, the identical
    documented per-tenant-resolution deferral Workflow Engine's own
    client already established) and relay its one full response as a
    single SSE chunk. This module's own SSE contract to ITS OWN callers
    is unaffected and still real; what's honest is only that the upstream
    hop to LLM Gateway isn't actually token-by-token, since LLM Gateway
    itself has no streaming route to relay from yet — a real perceived-
    streaming improvement needs LLM Gateway to grow one first, separately
    scoped.
  - `HTTPLLMGatewayClient.classify` called an invented `/v1/classify` —
    LLM Gateway has no classification endpoint. Fixed to ask the real
    `/chat/completions` for a JSON classification instead of inventing
    dedicated LLM Gateway surface; a non-JSON response degrades to an
    empty result, same as the existing "no refinement available" path
    `core/emotion.py`'s own caller already handles.
  - `HTTPGuardrailsClient.check` posted an invented `{content,
    policy_profile, tenant_id}` body and read an invented `{allowed,
    detail}` response. Fixed to the real `{text, stage}` body +
    `X-Tenant-Id` header / `{decision, violation_category, checks_run}`
    response — the identical real shape Workflow Engine's own
    `HTTPGuardrailsClient` already established for this exact port
    contract (ticket #82).
  - `HTTPHumanOversightClient.request_handoff` posted to an invented
    `/v1/oversight/handoff-request` and read an invented
    `human_oversight_ref_id` field. Fixed to the real
    `POST /v1/human-oversight/requests` / `{id}` response — again the
    identical real shape Workflow Engine's own client already
    established.
  - `HTTPLongTermMemoryClient.recall_identity_context` called an invented
    `GET /v1/memory/identity` — Long-Term Memory's real, and only,
    retrieval surface is `POST /v1/long-term-memory/query` (a
    scope+query-ranked search, not a fetch-by-user-id). Fixed, scoped to
    `user:{user_ref}` by convention (nothing else in this platform writes
    memories under that scope yet — this module's own job is to recall,
    not to author, those memories; a real write path is real,
    separately-scoped follow-up work, the same posture the assessment's
    own "memory governance" gap already names as open).
  - `HTTPObservabilityClient.emit` posted an invented `/v1/observability/events`
    with a raw business-event dict. Observability's real, and only,
    ingestion surface is `POST /v1/observability/ingest` (a trace_id plus
    OTel-shaped spans) — this module's own real trace pipeline already
    runs independently via OTel auto-instrumentation
    (`configure_tracing`), so this bespoke push both used the wrong shape
    AND duplicated a pipeline that already worked. Adapted rather than
    removed: each event becomes one real, zero-duration span carrying the
    full event as its `attributes`, so the call now succeeds and the
    event data stays queryable there.

  New `tests/unit/test_http_clients_real_wire_shapes.py` (respx-mocked,
  the same reference pattern Workflow Engine's own identically-named file
  already established) pins every fixed client's real wire contract so a
  future accidental revert fails immediately. New
  `tests/unit/test_routes_sessions.py` — no route-level test file existed
  for this module before this fix at all (every prior test exercised
  `SessionManager` directly, bypassing FastAPI); now covers every route,
  new and pre-existing, through a real app. `tests/integration/
  test_repository_postgres.py` gained real-Postgres coverage for
  `list_sessions`' aggregate COUNT + filtered page query and
  `delete_session`'s explicit cascade. `tests/unit/test_session_manager.py`
  gained identity-context-recall coverage (recalled for a returning user,
  not attempted for an anonymous one, fails open on a Long-Term Memory
  outage, and respects `cross_channel_continuity=false`).

  What this pass deliberately does NOT cover, per the assessment's own
  scoping: real per-tenant LLM Gateway virtual key resolution (one shared
  key today, same as Workflow Engine's own deferral); Long-Term Memory
  ever being WRITTEN to from a real conversation (this module only
  recalls); true token-by-token streaming from LLM Gateway (it has no
  streaming route yet); voice/WebSocket channel adapters (the LLD's own
  stack table names WebSocket for voice — this pass didn't touch channel
  adapters at all); and the broader "memory governance" gap (consent,
  purpose limitation, legal hold — that's Long-Term Memory's own module,
  a separate Phase 2 slice candidate, not attempted here).

- **The platform's own "unbounded offset" class** (this repo's own
  `CLAUDE.md`-documented recurring bug — already fixed for Billing and
  Metering's, LLM Gateway's, Multi-tenancy's and Workflow Engine's own
  `offset` query params; found again, still open here, when Evaluation
  Framework's own new contract-test tier hit the identical gap and a
  platform-wide grep confirmed it recurred everywhere else that hadn't
  already fixed it). `GET /`'s `offset` had no upper bound, so a
  value past Postgres's `bigint` range (`> 9223372036854775807`) crashed
  with an unhandled `asyncpg.DataError` instead of a clean `422`. Fixed
  with the identical `le=1_000_000_000` bound those four modules already
  use — comfortably past any real pagination need, comfortably under the
  overflow. Mechanical, not contract-tier-discovered here (this module
  has no contract tier of its own yet) — found by the platform-wide grep
  instead.

## Running locally

```bash
uv venv && uv pip install -e ".[dev]"
pytest                                                    # unit tests, no external services needed

docker compose -f deploy/docker-compose.yml up --build    # full stack incl. Postgres, Redis, dependency-stub
```
