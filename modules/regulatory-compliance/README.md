# Regulatory and Compliance — Module 17

Maps a single, once-implemented control (e.g. "human oversight on
high-risk decisions") to the specific clauses it satisfies across every
regulatory framework a tenant has enabled, and generates
framework-formatted evidence packs on demand. This module does not
implement controls itself — it maps and evidences controls implemented
by other modules (Human Oversight, Guardrails, Sentinel Agents, Workflow
Engine). Full design doc:
[`../../docs/module-17-regulatory-compliance.md`](../../docs/module-17-regulatory-compliance.md).

## Layout

```
src/regulatory_compliance/
  main.py                 FastAPI app, lifespan wiring (seeds the default crosswalk table), /healthz, /metrics
  app_context.py           Process-wide dependency container
  config.py                 Pydantic Settings — LLD config schema
  core/
    domain.py                FrameworkProfile/ControlMapping/ControlImplementationEvent/EvidencePack dataclasses
    mapping_data.py            The bundled default crosswalk table — the "living regulatory feed" data
    ports.py                    Repository, Auditability
    fakes.py                     In-memory implementations of every port, for unit tests
    crosswalk_engine.py           Crosswalk Engine + Coverage Calculator
    regulatory_feed.py             Regulatory Feed Manager — publishes/deprecates mapping-table versions
    evidence_generator.py           Evidence Pack Generator — real PDF (fpdf2) or JSON output
    evidence_worker.py               Durable evidence-pack worker — SELECT FOR UPDATE SKIP LOCKED poll loop
  db/                      SQLAlchemy 2.0 async models + repository
  clients/                 HTTP client for Auditability
  security/                 Service-to-service JWT bearer auth (shared signing key), the entitlement gate, real OpenAPI security scheme declarations
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI router — framework-profiles, mappings, control-events, coverage, evidence-packs
  schemas/                    Pydantic request/response models
```

## Design notes vs. the LLD

- **Resiliency.** Every outbound HTTP call this module makes to a peer module goes through `ResilientHTTPClient` (`clients/resilience.py`): exponential-backoff retry on network errors and 5xx responses (never 4xx — a client error means the peer already processed the request and rejected it, so retrying just repeats the mistake), and a circuit breaker (`aiobreaker`) that opens after repeated failures so a struggling peer gets a break instead of a retry storm, and this module fails fast instead of piling up requests against a peer that's already down.

- **Evidence pack PDF generation.** The LLD's "PDF (via the platform's
  own PDF generation approach)" is realised with `fpdf2` — a genuinely
  lightweight, pure-Python PDF writer with no system dependencies, so
  this is real PDF byte generation, not a text-file stand-in. `document_format:
  json` is also supported per the LLD's config (`evidence.output_format`).
- **Control events source.** The LLD's Level 2 diagram has Human
  Oversight/Guardrails/Workflow Engine publish control events to
  Auditability, which this module then queries. This module's own `POST
  /control-events` still accepts direct ingestion from source modules —
  kept as its own path rather than being retired now that Module 20
  (Auditability) exists, since it's the same shape either way and gives
  a source module a choice of where to write. `HTTPAuditabilityClient.
  query_control_events` targets Auditability's real `GET /v1/
  auditability/events` for best-effort evidence-pack enrichment; every
  call site treats a failure as "no enrichment available," never as a
  reason to fail generation, since this module's
  own `ControlImplementationEvent` rows remain the evidence source of
  record either way.
- **Async evidence generation — durable, not in-process.** `POST
  /evidence-packs` returns immediately with `status=generating`; that
  record IS the queue entry. This used to be a real FastAPI
  `BackgroundTasks` job — genuine async work, but non-durable: a pod
  restart between the 202 response and the background task finishing
  left the pack stuck at `status=generating` forever, since nothing else
  would ever pick it back up. Fixed by `core/evidence_worker.py`'s
  `EvidencePackWorker`: an asyncio poll loop (started in `main.py`'s
  lifespan) claiming pending packs via a real Postgres `SELECT ... FOR
  UPDATE SKIP LOCKED` query, so multiple worker instances/pods can poll
  the same table concurrently without ever double-claiming a row. Each
  claim gets a time-bounded lease; a worker that crashes mid-generation
  simply lets that lease expire, and the next poll (from any instance)
  reclaims the job — no separate liveness check needed. A startup
  recovery sweep force-expires every held lease immediately, so anything
  left mid-flight by a now-dead previous process instance is reclaimed
  on the very next poll tick rather than waiting out its lease. A
  generation failure with attempts remaining is requeued for retry;
  once `evidence.worker_max_attempts` is exhausted the pack is marked
  `failed` for good (`last_error` explains why) instead of being retried
  forever. See `tests/integration/test_evidence_worker_postgres.py` for
  the concurrency property this actually depends on, proven against a
  real Postgres — `FOR UPDATE SKIP LOCKED` can't be meaningfully tested
  against SQLite or an in-memory fake.
- **Crosswalk mapping table.** `core/mapping_data.py` ships a default
  crosswalk covering the controls this platform's other governance
  modules already implement (human oversight, guardrails policy checks,
  sentinel monitoring, audit logging, workflow confidence-gating, PII
  redaction, right-to-erasure) against EU AI Act, NIST AI RMF, ISO 42001,
  DORA **and GDPR**. GDPR was missing from the first cut of this table —
  a real gap, not a deliberate scoping decision, caught in review — and is
  now mapped against four controls this platform already implements:
  Long-Term Memory's provable right-to-erasure flow (Art.17), Guardrails'
  PII redaction (Art.5(1)(c), Art.25), Human Oversight's approval queue
  (Art.22, the automated-decision-making safeguard), and Auditability's
  event log (Art.30, Art.5(2)). `RegulatoryFeedManager`
  reads config-driven mapping data (this file today; `mapping_table_path`
  can point at an operator-supplied YAML file), matching the LLD's
  "living regulatory feed" claim that a new framework or delegated act is
  a data change, not a code change. `POST /mappings/publish` is the
  feed-update endpoint from LLD §Level 3's "regulatory feed update"
  sequence — it deprecates (never deletes) prior-version rows for the
  frameworks it touches, so a tenant pinned to an older
  `FrameworkProfile.version` is unaffected until they explicitly opt in
  to the newer version.
- **Postgres integration tests.** The repository layer is now also
  tested against a real Postgres (`tests/integration/`, opt-in via
  `TECTONIC_TEST_POSTGRES_URL` or Docker+testcontainers), covering real
  JSONB list round-tripping of `ControlMapping.clause_references`, the
  `deprecate_control_mappings` multi-row update touching only the
  targeted framework version, and a real UUID primary key round trip
  through `FrameworkProfile`/`EvidencePack` — none of which SQLite's
  unit-tier fakes can reliably prove. See `tests/integration/conftest.py`
  for how the Postgres instance is obtained. This tier's presence
  prompted a platform-wide sweep of every module's `db/models.py` for
  the same class of bug: `Mapped[datetime]` columns missing
  `DateTime(timezone=True)` despite the Alembic migration already
  defining them as timestamptz and the domain layer's defaults being
  tz-aware — invisible under SQLite, but a real correctness bug against
  Postgres once a domain default (or an explicit value) is written.
  Found and fixed here too.

- **`GET /mappings` pagination.** Added `limit`/`offset` query params
  (default `limit=50`, max `200`) — the response shape changed from a bare
  array to `ControlMappingListResponse` (`items`/`total`/`limit`/`offset`).
  Results are ordered by `id` ascending for a stable page boundary (there's
  no timestamp column on `control_mappings` to order by instead). The
  repository-level `list_control_mappings` method itself gained
  `limit`/`offset` and now returns `(items, total)`; its two internal
  callers — `CrosswalkEngine.map_control` and `CoverageCalculator.coverage`
  — need the *complete* matching set to crosswalk/score correctly, so they
  call it with `limit=10_000` (an effectively-unbounded internal page size
  for this small, config-driven mapping table) rather than truncating to
  the API's default page size.
- **Connection pooling tuned to replica count.** SQLAlchemy's out-of-
  the-box defaults (`pool_size=5`, `max_overflow=10`) are the same
  regardless of how many pods are running — at this module's own
  `deploy/helm/regulatory-compliance/values.yaml` `autoscaling.maxReplicas: 10`,
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
- **Pagination on `GET /mappings`.** Added `limit`/`offset` query params
  (default 50, max 200) and a `ControlMappingListResponse` envelope
  (`items`/`total`/`limit`/`offset`) — this endpoint previously returned
  every matching mapping row unbounded. `ControlMapping` has no natural
  timestamp column, so this orders by `id` ascending as a stable,
  deterministic tiebreaker. `CrosswalkEngine.map_control` and
  `CoverageCalculator.coverage` are internal callers of the same
  repository method that genuinely need the *complete* matching set (a
  truncated page would silently drop mappings or skew a coverage
  percentage) — both pass `limit=10_000`, an effectively-unbounded
  internal page size, not a real pagination boundary, since mapping
  tables per control/framework are small, config-driven data rather
  than a user-growable list.

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
  `HTTPAuditabilityClient` makes — a token minted to call one peer is
  rejected if replayed against a different one. The shared secret
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
  entitle), it calls Multi-tenancy's real `GET /tenants/{id}/gate?module=regulatory-compliance`,
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
