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
  security/                 Service-to-service JWT bearer auth (shared signing key)
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI routers — sessions, turn (SSE or JSON), handoff, close
  schemas/                    Pydantic request/response models
```

## Design notes vs. the LLD

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
  Module 20, Auditability, which hasn't been built yet, same
  aspirational-target pattern used elsewhere) make — a token minted to
  call one peer is rejected if replayed against a different one. The
  shared secret (`TECTONIC_JWT_SHARED_SECRET`, one Kubernetes Secret
  referenced by every module's Helm chart under this same literal env
  var name, not a per-module-prefixed one) defaults to an obviously-
  insecure placeholder for zero-config local dev/tests; `main.py` logs a
  startup warning if it's still active. This is service-to-service auth
  for inter-module calls, not the platform's external-facing user-auth
  story — a real API gateway/OAuth layer in front of the platform's own
  entry points is a separate, larger concern, out of scope here.

## Running locally

```bash
uv venv && uv pip install -e ".[dev]"
pytest                                                    # unit tests, no external services needed

docker compose -f deploy/docker-compose.yml up --build    # full stack incl. Postgres, Redis, dependency-stub
```
