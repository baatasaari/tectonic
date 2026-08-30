# Intent Detection — Module 5

The first classification step in most conversational and workflow paths:
given raw input and context, determines what the user is actually trying
to do, so the Conversational Engine or Workflow Engine can route
correctly. Classifies and hands off — it does not generate responses or
execute actions. Full design doc:
[`../../docs/module-05-intent-detection.md`](../../docs/module-05-intent-detection.md).

## Layout

```
src/intent_detection/
  main.py                 FastAPI app, lifespan wiring, /healthz, /metrics
  app_context.py           Process-wide dependency container
  config.py                 Pydantic Settings — LLD config schema
  core/
    domain.py                IntentTaxonomy/ClassificationLog/DriftReport dataclasses
    ports.py                   Repository, LLM Gateway fallback client
    fakes.py                    In-memory implementations of every port, for unit tests
    similarity.py                 Term-frequency cosine similarity — the Primary Classifier's scorer
    primary_classifier.py          Primary Classifier — fast single-pass scoring against the taxonomy
    compositional_decomposer.py     Compositional Decomposer — multi-intent signal detection
    llm_fallback.py                  LLM Fallback Handler
    drift_monitor.py                  Drift Monitor — Population Stability Index
    classification_service.py         The classification orchestrator (this module's "scheduler")
  db/                      SQLAlchemy 2.0 async models + repository
  clients/                 HTTP client for the LLM Gateway fallback dependency
  security/                 Service-to-service JWT bearer auth (shared signing key), the entitlement gate, real OpenAPI security scheme declarations
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI routers — classify, taxonomies, drift-reports
  schemas/                    Pydantic request/response models
```

## Design notes vs. the LLD

- **Resiliency.** Every outbound HTTP call this module makes to a peer module goes through `ResilientHTTPClient` (`clients/resilience.py`): exponential-backoff retry on network errors and 5xx responses (never 4xx — a client error means the peer already processed the request and rejected it, so retrying just repeats the mistake), and a circuit breaker (`aiobreaker`) that opens after repeated failures so a struggling peer gets a break instead of a retry storm, and this module fails fast instead of piling up requests against a peer that's already down.

- **Primary Classifier.** The LLD calls for "a fine-tuned small model (e.g.
  a distilled transformer classifier)." `core/primary_classifier.py` scores
  each taxonomy intent by its closest labelled example via term-frequency
  cosine similarity (`core/similarity.py`) instead — a genuine local
  classifier with no external model-serving dependency, so unit and
  integration tests never depend on bundled model weights. Swapping in a
  real fine-tuned model means implementing the same `classify` interface.
- **Drift Monitor.** Implements Population Stability Index directly (one
  formula, not worth a stats library dependency) comparing the observed
  distribution of detected intents against a baseline approximated from
  each intent's labelled-example share — this module has no separate
  "training set" artifact to compare against.
- **Privacy by design.** Raw input text is never persisted — only
  `hash_input()`'s SHA-256 hash, per the LLD's `ClassificationLog.input_hash`
  field and its stated rationale.
- **Postgres integration tests** — the repository layer is now also tested
  against a real Postgres (`tests/integration/`, opt-in via
  `TECTONIC_TEST_POSTGRES_URL` or Docker+testcontainers), covering
  `IntentTaxonomy.intents` / `ClassificationLog.intents_detected` JSONB
  round-tripping (nested lists-of-dicts, exact float confidence values), a
  real UUID primary key, and a multi-row `get_taxonomy_by_version`/
  `get_active_taxonomy` query that must select only the intended
  tenant+version/status row among several taxonomies — all things SQLite's
  unit-tier fakes can't reliably prove. See `tests/integration/conftest.py`
  for how the Postgres instance is obtained. This tier's presence prompted a
  platform-wide sweep of every module's `db/models.py` for the same class of
  bug: `Mapped[datetime]` columns missing `DateTime(timezone=True)` despite
  the Alembic migration already defining them as timestamptz and the domain
  layer's defaults being tz-aware — invisible under SQLite, but a real
  correctness bug against Postgres once a domain default (or an explicit
  value) is written. Found and fixed here too.

- **Connection pooling tuned to replica count.** SQLAlchemy's out-of-
  the-box defaults (`pool_size=5`, `max_overflow=10`) are the same
  regardless of how many pods are running — at this module's own
  `deploy/helm/intent-detection/values.yaml` `autoscaling.maxReplicas: 20`,
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
- **Pagination on `GET /drift-reports`.** Added `limit`/`offset` query
  params (default 50, max 200) and a `DriftReportListResponse` envelope
  (`items`/`total`/`limit`/`offset`) — this endpoint previously returned
  every matching row unbounded, and drift reports accumulate per tenant
  over the life of a taxonomy. Ordered by `created_at` descending
  (newest report first).

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
  *specific* peer being called on every outbound request `HTTPLLMGatewayClient`
  makes — a token minted to call one peer is rejected if replayed against
  a different one. The shared secret (`TECTONIC_JWT_SHARED_SECRET`, one
  Kubernetes Secret referenced by every module's Helm chart under this
  same literal env var name, not a per-module-prefixed one) defaults to
  an obviously-insecure placeholder for zero-config local dev/tests;
  `main.py` logs a startup warning if it's still active. This is
  service-to-service auth for inter-module calls, not the platform's
  external-facing user-auth story — a real API gateway/OAuth layer in
  front of the platform's own entry points is a separate, larger
  concern, out of scope here.

- **Enforces its own subscription entitlement via `EntitlementGateMiddleware`**
  (`security/entitlement_gate.py`) — see Agent Cards' README and the rollout
  playbook doc (`docs/entitlement-gate-rollout.md`) for the shared reference
  implementation. Layered after `ServiceAuthMiddleware` (authenticate, then
  entitle), it calls Multi-tenancy's real `GET /tenants/{id}/gate?module=intent-detection`,
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

- **NUL bytes in a raw string query parameter reaching the database
  unvalidated** (ticket #82's platform-wide sweep, following the same bug
  a real CI run found on Multi-tenancy's and Billing and Metering's own
  contract tiers — see either module's own README for the original
  finding; this module wasn't in that sweep's original module list —
  found by re-grepping the whole platform for the same pattern once the
  sweep was otherwise done). `GET /drift-reports`'s `tenant_id` never
  ran through a NUL-byte validator — a plain, un-wrapped `str` function
  parameter rather than an explicit `Query()` default, which is why the
  earlier grep for `Query(` missed this file; fixed with
  `_reject_null_byte_query()`. No route-level test file existed for
  this module before this fix — `tests/unit/test_routes_intents.py`
  (new) pins just this regression; comprehensive route coverage remains
  a real, separately-scoped gap.

## Running locally

```bash
uv venv && uv pip install -e ".[dev]"
pytest                                                    # unit tests, no external services needed

docker compose -f deploy/docker-compose.yml up --build    # full stack incl. Postgres, dependency-stub
```
