# Sentinel Agents — Module 15

Watches the platform's own agents at runtime, independent of Guardrails
(individual input/output checks) and Evaluation Framework (quality
scoring). Concerned with behaviour over time and across agents: is this
agent acting outside its normal envelope, and are multiple agents
together producing an emergent problem no single one would trigger
alone. Full design doc:
[`../../docs/module-15-sentinel-agents.md`](../../docs/module-15-sentinel-agents.md).

## Layout

```
src/sentinel_agents/
  main.py                 FastAPI app, lifespan wiring, /healthz, /metrics
  app_context.py           Process-wide dependency container
  config.py                 Pydantic Settings — LLD config schema
  core/
    domain.py                AgentBaseline/Alert/InterventionRecord/SwarmCorrelationWindow dataclasses
    ports.py                   Repository, Workflow Engine, Tool Orchestration, Human Oversight, Auditability
    fakes.py                    In-memory implementations of every port, for unit tests
    stats.py                      Welford's online mean/variance algorithm
    baseliner.py                   Behavioural Baseliner — per-agent z-score deviation detection
    swarm_correlation.py            Swarm Correlation Engine — cross-agent windowed correlation
    decision_engine.py               Intervention Decision Engine — alert/autonomous/escalate
    event_processor.py                The orchestrator tying every component together per event
  db/                      SQLAlchemy 2.0 async models + repository
  clients/                 HTTP clients for Workflow Engine, Tool Orchestration, Human Oversight, Auditability
  security/                 Service-to-service JWT bearer auth (shared signing key), the entitlement gate, real OpenAPI security scheme declarations
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI router — events, alerts, baselines, config
  schemas/                    Pydantic request/response models
```

## Design notes vs. the LLD

- **Resiliency.** Every outbound HTTP call this module makes to a peer module goes through `ResilientHTTPClient` (`clients/resilience.py`): exponential-backoff retry on network errors and 5xx responses (never 4xx — a client error means the peer already processed the request and rejected it, so retrying just repeats the mistake), and a circuit breaker (`aiobreaker`) that opens after repeated failures so a struggling peer gets a break instead of a retry storm, and this module fails fast instead of piling up requests against a peer that's already down.

- **Agent runtime.** The LLD calls for Google ADK 2.0 `Agent` since
  Sentinels are themselves agents. Following the same precedent as
  Module 1 (Workflow Engine), this is a self-contained implementation
  rather than a dependency on ADK 2.0, which isn't installable/runnable
  in this build environment.
- **Event ingestion.** The LLD calls for `aiokafka` consuming from a
  Kafka/Redpanda event bus. No broker is available in this build
  environment, so `POST /v1/sentinel-agents/events` is a synchronous
  HTTP ingestion endpoint standing in for the Kafka consumer — other
  modules (or a Kafka-to-HTTP bridge in a real deployment) POST events
  to it directly. Every downstream stage (baselining, swarm correlation,
  decision, intervention) is unaffected by this choice; only the
  transport differs.
- **Behavioural baselining.** Implements the LLD's own stated default —
  "statistical process control (rolling mean/variance per agent per
  action type)" — via Welford's online algorithm, with z-score
  thresholds tuned by the `low`/`medium`/`high` sensitivity config. The
  optional isolation-forest tier for higher-volume tenants is a
  documented gap, not implemented.
- **Swarm window state.** The correlation window is held in a single
  long-lived in-process tracker (`SwarmWindowTracker`, constructed once
  in `AppContext`), not a shared store. Correct for a single instance,
  but a multi-replica deployment consuming different Kafka partitions
  would each see only part of the swarm signal — a shared window (Redis,
  or tenant-based partitioning) would be needed for production
  horizontal scale.
- **Tool Orchestration circuit-break target.** The LLD's Decision Engine
  calls "Tool Orchestration's circuit breaker" as an intervention target.
  Module 4 (Tool Orchestration)'s own LLD and API surface never define an
  externally triggerable circuit-break endpoint — its breaker only opens
  from call failures it observes internally. `HTTPToolOrchestrationClient
  .circuit_break()` calls a plausible-but-not-yet-real endpoint and treats
  a failure as best-effort (logged, not raised), the same documented-gap
  pattern used for Long-Term Memory's Graph DB erasure call.
- **`POST /config` runtime overrides.** Accepted for API-surface
  completeness but doesn't persist a per-tenant override in this build —
  configuration is sourced from this module's own YAML/env at startup,
  with `baselining.sensitivity` marked hot-reloadable there.
- **Postgres integration tests.** The repository layer is now also tested
  against a real Postgres (`tests/integration/`, opt-in via
  `TECTONIC_TEST_POSTGRES_URL` or Docker+testcontainers), covering
  `Alert.agent_refs` JSONB round-tripping, an upsert-style query
  (`upsert_baseline`) that must update only the one row matching a real
  multi-column uniqueness constraint (`tenant_id`, `agent_ref`, `action_type`)
  rather than creating a duplicate, and a multi-row filtered query
  (`list_alerts` scoped by severity) — none of which SQLite's unit-tier fakes
  can reliably prove. See `tests/integration/conftest.py` for how the Postgres
  instance is obtained. This tier's presence prompted a platform-wide sweep of
  every module's `db/models.py` for the same class of bug: `Mapped[datetime]`
  columns missing `DateTime(timezone=True)` despite the Alembic migration
  already defining them as timestamptz and the domain layer's defaults being
  tz-aware — invisible under SQLite, but a real correctness bug against
  Postgres once a domain default (or an explicit value) is written. Found and
  fixed here too.

- **`GET /alerts` pagination.** Added `limit`/`offset` query params
  (default `limit=50`, max `200`); the response shape changed from a
  bare array to `AlertListResponse` (`items`/`total`/`limit`/`offset`).
  Alerts are a genuinely growing per-tenant history, so this is real
  limit/offset pagination end to end (`SentinelRepository.list_alerts`
  now returns `(items, total)`). Ordered by `detected_at` descending
  (newest first, the useful default for an alert feed) with `id`
  ascending as a tiebreaker, since multiple alerts can share a
  `detected_at` timestamp.
- **`GET /baselines/{agent_ref}` pagination deliberately skipped.**
  `AgentBaselineRecord` rows are keyed by `(tenant_id, agent_ref,
  action_type)` and updated in place by `upsert_baseline` (Welford's
  running mean/variance) — never appended to. One agent's baseline list
  is therefore bounded by its small, fixed set of distinct action types,
  not an unbounded growing history the way `/alerts` is, so it was left
  returning a bare `list[BaselineSchema]` rather than adding limit/offset
  pagination that would add API surface with no real capacity problem to
  solve. See the docstring on `SentinelRepository.list_baselines_for_agent`
  in `core/ports.py`.
- **Connection pooling tuned to replica count.** SQLAlchemy's out-of-
  the-box defaults (`pool_size=5`, `max_overflow=10`) are the same
  regardless of how many pods are running — at this module's own
  `deploy/helm/sentinel-agents/values.yaml` `autoscaling.maxReplicas: 20`,
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
  `HTTPWorkflowEngineClient`, `HTTPToolOrchestrationClient`,
  `HTTPHumanOversightClient` and `HTTPAuditabilityClient` make — a token
  minted to call one peer is rejected if replayed against a different
  one. The shared secret (`TECTONIC_JWT_SHARED_SECRET`, one Kubernetes
  Secret referenced by every module's Helm chart under this same literal
  env var name, not a per-module-prefixed one) defaults to an obviously-
  insecure placeholder for zero-config local dev/tests; `main.py` logs a
  startup warning if it's still active. This is service-to-service auth
  for inter-module calls, not the platform's external-facing user-auth
  story — a real API gateway/OAuth layer in front of the platform's own
  entry points is a separate, larger concern, out of scope here.

- **Enforces its own subscription entitlement via `EntitlementGateMiddleware`**
  (`security/entitlement_gate.py`) — see Agent Cards' README and the rollout
  playbook doc (`docs/entitlement-gate-rollout.md`) for the shared reference
  implementation. Layered after `ServiceAuthMiddleware` (authenticate, then
  entitle), it calls Multi-tenancy's real `GET /tenants/{id}/gate?module=sentinel-agents`,
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

docker compose -f deploy/docker-compose.yml up --build    # full stack incl. Postgres, dependency-stub
```
