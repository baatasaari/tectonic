# Workflow Engine — Module 1

Executes agent workflows defined as directed graphs, combining deterministic
symbolic step routing with neural/LLM-driven steps, human-in-the-loop
checkpoints, and confidence-gated autonomy. Full low-level design:
[`../../docs/module-01-workflow-engine-lld.md`](../../docs/module-01-workflow-engine-lld.md).

## Layout

```
src/workflow_engine/
  main.py              FastAPI app, lifespan wiring, /healthz, /metrics
  app_context.py        Process-wide dependency container
  config.py              Pydantic Settings — LLD §4.5 config schema
  core/                   Framework-agnostic domain logic
    domain.py             Dataclasses: graph, instance, step, approval, replan event
    ports.py              Abstract interfaces the engine depends on (repository,
                           event publisher, LLM Gateway/Tool Orchestration/
                           Guardrails/Human Oversight clients)
    fakes.py               In-memory implementations of every port, for unit tests
    parser.py              Definition Parser/Validator — schema + graph validation
    router.py              Step Router — symbolic/neural/human/auto resolution
    symbolic.py             Symbolic Rule Executor — safe-eval rule DSL
    neural.py                Neural Step Executor — LLM Gateway/Tools/Guardrails
    human.py                  Human Approval Handler
    replanner.py               Replanner — structural (symbolic) + content (neural) adaptation
    scheduler.py                Execution Scheduler — the graph runtime
    events.py                    Event topic/payload builders
  db/                     SQLAlchemy 2.0 async models + repository
  clients/                Kafka publisher, HTTP clients for the 4 external modules
  security/                Service-to-service JWT bearer auth (shared signing key)
  telemetry/               OTel tracing, Prometheus metrics, structlog logging
  api/                     FastAPI routers (LLD §3.3)
  schemas/                  Pydantic request/response models
alembic/                 DB migrations
stubs/dependency-stub/   Stand-in HTTP service for LLM Gateway / Tool
                          Orchestration / Guardrails / Human Oversight
deploy/                  docker-compose (stub profile), Helm chart, Prometheus alerts
tests/unit/              Unit tests against in-memory fakes (no external services)
tests/integration/        Real-Postgres tier via testcontainers (needs Docker)
```

## Design notes vs. the LLD

- **Resiliency.** Every outbound HTTP call this module makes to a peer module goes through `ResilientHTTPClient` (`clients/resilience.py`): exponential-backoff retry on network errors and 5xx responses (never 4xx — a client error means the peer already processed the request and rejected it, so retrying just repeats the mistake), and a circuit breaker (`aiobreaker`) that opens after repeated failures so a struggling peer gets a break instead of a retry storm, and this module fails fast instead of piling up requests against a peer that's already down.

- **ADK 2.0 Workflow Runtime.** The LLD names Google ADK 2.0's Workflow
  Runtime as the production graph executor. `core/scheduler.py` implements
  the same semantics (fan-out/fan-in, retry, confidence-gated human-in-the-
  loop, replanning) as a self-contained runtime rather than a hard dependency
  on that SDK, so the module builds, runs and is fully unit-tested today
  without an external agent-runtime package. The Definition Parser already
  keeps the platform-level workflow schema independent of whatever graph
  representation drives execution underneath (LLD §3.2); swapping in the
  real ADK 2.0 Workflow Runtime means implementing `ExecutionScheduler`'s
  role against ADK's graph executor and Task API, without touching the
  parser, the schema, or any of the step executors.
- **Symbolic rule engine.** The LLD names `durable-rules`/Nools with an
  explicit fallback: "a lightweight custom rule DSL compiled to Python
  callables if third-party engine proves too heavyweight." `core/symbolic.py`
  takes that fallback — rules are boolean expressions over the step's input
  context, evaluated by a restricted AST walker (no third-party rule engine
  dependency, no `eval`).
- **Single-pending-approval simplification.** The current scheduler assumes
  at most one step per instance is ever awaiting human approval at a time.
  Multi-concurrent-approval support is a follow-up, not a change to the
  state model.
- **Multi-tenancy.** Tenant is resolved from an `X-Tenant-Id` header,
  falling back to the deployment's configured default tenant. A real
  deployment sits this behind whatever the platform's auth layer resolves
  tenant from.
- **Postgres integration tests, now dual-path.** `tests/integration/`
  previously required Docker/testcontainers only; it now also accepts
  `TECTONIC_TEST_POSTGRES_URL` against an already-running Postgres (see
  `tests/integration/conftest.py`), matching the pattern used across the
  rest of the platform. Running it for real for the first time (Docker
  was never available in the environment this module was originally
  built in) surfaced a genuine schema-drift bug: every `Mapped[datetime]`
  column in `db/models.py` (`published_at`, `started_at`, `completed_at`,
  `requested_at`, `resolved_at`, `created_at`) was missing
  `DateTime(timezone=True)`, even though every Alembic migration already
  defines them as timestamptz and the domain layer's defaults are all
  tz-aware. Invisible under SQLite; asyncpg rejected the mismatch for
  real. Fixed in `db/models.py`.

- **Connection pooling tuned to replica count.** SQLAlchemy's out-of-
  the-box defaults (`pool_size=5`, `max_overflow=10`) are the same
  regardless of how many pods are running — at this module's own
  `deploy/helm/workflow-engine/values.yaml` `autoscaling.maxReplicas: 10`,
  that's up to 150 connections to this module's own Postgres
  instance from this module alone at full autoscale, with no one having
  deliberately decided that number. `db/session.py`'s `make_engine` now
  passes explicit, configurable `pool_size=10` /
  `max_overflow=5` (`db_pool_size`/`db_max_overflow`
  Settings, env-overridable) sized so this module's own steady-state
  total stays at ~100 connections and its full-burst total at ~150,
  even at `maxReplicas`. `pool_recycle=1800s` also avoids stale
  connections behind a cloud LB/proxy's own idle-connection timeout —
  a real, independent gap, not just a replica-count one.
- **Pagination on `GET /{instance_id}/steps`.** Added `limit`/`offset`
  query params (default 50, max 200) and a `StepExecutionListResponse`
  envelope (`items`/`total`/`limit`/`offset`) — this endpoint previously
  returned every step execution for an instance unbounded, a real
  scaling gap for a long-running or heavily-replanned workflow instance.
  Neither `started_at` nor `completed_at` is a reliable ordering column
  (both are nullable — a pending step has neither), so this orders by
  `id` ascending instead, a stable, deterministic tiebreaker so
  limit/offset pagination is actually meaningful. `GET
  /{instance_id}` (the instance detail view, which embeds the complete
  step list inline) is a distinct, intentionally-unpaginated internal
  call against the same repository method (`limit=10_000`, an
  effectively-unbounded internal page size) — that view genuinely needs
  the complete list, not one page of it.

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
  four HTTP clients (`HTTPLLMGatewayClient`, `HTTPToolOrchestrationClient`,
  `HTTPGuardrailsClient`, `HTTPHumanOversightClient`) make — a token
  minted to call one peer is rejected if replayed against a different
  one. The shared secret (`TECTONIC_JWT_SHARED_SECRET`, one Kubernetes
  Secret referenced by every module's Helm chart under this same literal
  env var name, not a per-module-prefixed one) defaults to an obviously-
  insecure placeholder for zero-config local dev/tests; `main.py` logs a
  startup warning if it's still active. This is service-to-service auth
  for inter-module calls, not the platform's external-facing user-auth
  story — a real API gateway/OAuth layer in front of the platform's own
  entry points is a separate, larger concern, out of scope here.

## Running locally

```bash
uv venv && uv pip install -e ".[dev]"
pytest                                   # unit tests, no external services needed

docker compose -f deploy/docker-compose.yml up --build   # full stack incl. Postgres,
                                                           # Redpanda, dependency-stub
```

## Testing tiers (LLD §4.8)

| Tier | What it needs | How to run |
|---|---|---|
| Unit | Nothing — in-memory fakes only | `pytest tests/unit` |
| Integration (isolated) | Docker (Postgres via testcontainers) | `pytest tests/integration` |
| Contract | Running instance + `schemathesis` | not yet wired into CI here |
| Load | Running instance + `locust` | not yet wired into CI here |
