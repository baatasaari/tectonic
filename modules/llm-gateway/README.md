# LLM Gateway — Module 3

The only module permitted to call model providers directly. Every other
module that needs LLM inference goes through this gateway — never a
provider SDK directly — which is what makes provider swaps, cost governance
and quality routing possible platform-wide. Full design doc:
[`../../docs/module-03-llm-gateway.md`](../../docs/module-03-llm-gateway.md).

## Layout

```
src/llm_gateway/
  main.py                 FastAPI app, lifespan wiring, /healthz, /metrics
  app_context.py           Process-wide dependency container
  config.py                 Pydantic Settings — LLD config schema
  core/
    domain.py                VirtualKey/BudgetPolicy/RequestLog/ProviderConfig dataclasses
    ports.py                   Repository, cache, quality-score feed, provider client, secrets
    fakes.py                    In-memory implementations of every port, for unit tests
    normalizer.py                 Request Normalizer
    similarity.py                  Shared term-frequency cosine similarity for the cache
    semantic_cache.py               Semantic Cache — in-memory (tests) and Redis (prod) impls
    router.py                        Quality-Aware Router
    cost_governance.py                Cost Governance Engine
    failover.py                        Failover Manager
    gateway_service.py                  The request orchestrator (this module's "scheduler")
    deprecation_watcher.py               Model Deprecation Watcher
  db/                      SQLAlchemy 2.0 async models + repository
  clients/                 HTTP provider adapter, Redis quality-score store, Secrets client
  security/                 Service-to-service JWT bearer auth (shared signing key), the entitlement gate, real OpenAPI security scheme declarations
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI routers — OpenAI-compatible completions/embeddings, admin
  schemas/                    Pydantic request/response models
```

## Design notes vs. the LLD

- **Resiliency.** Every outbound HTTP call this module makes to a peer module goes through `ResilientHTTPClient` (`clients/resilience.py`): exponential-backoff retry on network errors and 5xx responses (never 4xx — a client error means the peer already processed the request and rejected it, so retrying just repeats the mistake), and a circuit breaker (`aiobreaker`) that opens after repeated failures so a struggling peer gets a break instead of a retry storm, and this module fails fast instead of piling up requests against a peer that's already down.

- **Provider adapter.** The LLD names LiteLLM as the provider abstraction.
  `clients/http_provider_client.py` implements `ProviderClient` as a generic
  OpenAI-compatible HTTP adapter instead of importing the `litellm` package
  directly: every `ProviderConfig.endpoint` already models a per-provider
  base URL, and OpenAI-compatible `/chat/completions` is what the large
  majority of providers and proxies speak today — including LiteLLM's own
  proxy mode, so pointing a `ProviderConfig` at a running LiteLLM proxy is a
  drop-in way to get its 100+-provider coverage. Swapping in the `litellm`
  Python SDK directly means implementing the same `ProviderClient` Protocol
  against `litellm.acompletion` — same boundary Module 1 draws around ADK.
- **Semantic cache.** RedisVL (real embeddings + ANN search) is the LLD's
  production choice; `core/similarity.py` implements a lightweight local
  term-frequency cosine similarity instead, so caching works without a
  network round-trip to an embedding model on every lookup. Staleness
  awareness is a `stale` flag per entry a drift-detection signal can set
  (`flag_stale`/`invalidate_stale`), rather than a fixed TTL.
- **Quality-aware router.** Cost and latency aren't separately tracked
  fields in the LLD's `ProviderConfig` data model, so the router uses each
  provider's `priority` as a shared proxy for both, blended with the live
  quality score from the (stubbed, until Module built) Evaluation
  Framework feed per the configured strategy weights.
- **Cost governance.** Implements optimistic reserve-then-settle: an
  estimated ceiling is reserved against the budget before the provider call
  (so two concurrent requests can't both slip under a limit that only one
  should), then settled to the real cost once the provider responds.
- **Postgres integration tests** — the repository layer is now also tested
  against a real Postgres (`tests/integration/`, opt-in via
  `TECTONIC_TEST_POSTGRES_URL` or Docker+testcontainers), covering
  `provider_scope` / `deprecation_notices` JSONB round-tripping, a real UUID
  primary key, and a multi-row `list_virtual_keys` query that must hit only
  the intended tenant's rows — all things SQLite's unit-tier fakes can't
  reliably prove. See `tests/integration/conftest.py` for how the Postgres
  instance is obtained. This tier's presence prompted a platform-wide sweep of
  every module's `db/models.py` for the same class of bug: `Mapped[datetime]`
  columns missing `DateTime(timezone=True)` despite the Alembic migration
  already defining them as timestamptz and the domain layer's defaults being
  tz-aware — invisible under SQLite, but a real correctness bug against
  Postgres once a domain default (or an explicit value) is written. Found and
  fixed here too.

- **Connection pooling tuned to replica count.** SQLAlchemy's out-of-
  the-box defaults (`pool_size=5`, `max_overflow=10`) are the same
  regardless of how many pods are running — at this module's own
  `deploy/helm/llm-gateway/values.yaml` `autoscaling.maxReplicas: 30`,
  that's up to 450 connections to this module's own Postgres
  instance from this module alone at full autoscale, with no one having
  deliberately decided that number. `db/session.py`'s `make_engine` now
  passes explicit, configurable `pool_size=4` /
  `max_overflow=2` (`db_pool_size`/`db_max_overflow`
  Settings, env-overridable) sized so this module's own steady-state
  total stays at ~100 connections and its full-burst total at ~150,
  even at `maxReplicas`. `pool_recycle=1800s` also avoids stale
  connections behind a cloud LB/proxy's own idle-connection timeout —
  a real, independent gap, not just a replica-count one.
- **Pagination on `GET /virtual-keys`.** Added `limit`/`offset` query
  params (default 50, max 200) and a `VirtualKeyListResponse` envelope
  (`items`/`total`/`limit`/`offset`) — virtual keys are tenant-scoped and
  accumulate over the life of a tenant, and this endpoint previously
  returned every matching row unbounded. Ordered by `created_at`
  descending (newest key first).
- **`GET /providers` deliberately left unpaginated.** Provider configs
  are a fixed, admin-configured set of LLM providers this gateway
  integrates with — one row per provider it knows how to call
  (OpenAI, Anthropic, etc.) — not a tenant-scoped dataset that grows
  with usage. `ProviderConfigRecord` has no `tenant_id` and
  `list_provider_configs()` takes no filters; in practice this is a
  handful of rows, so `limit`/`offset` would add API surface without a
  real bound to enforce. See the comment at the route in
  `api/routes_admin.py`. Revisit if provider configs ever become
  tenant-configurable.

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
  the *specific* peer being called on every outbound request
  `HTTPSecretsClient` makes to Secrets and Credential Management (not yet
  built in this platform — same aspirational-target pattern used
  elsewhere) — a token minted to call one peer is rejected if replayed
  against a different one. `HTTPProviderClient` is deliberately excluded:
  it calls real external LLM provider APIs, not a platform peer, and
  those already authenticate via their own API keys. The shared secret
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
  entitle), it calls Multi-tenancy's real `GET /tenants/{id}/gate?module=llm-gateway`,
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

- **Real pre-flight quota check against Multi-tenancy's `POST
  /tenants/{id}/quota/check`, on every `complete()` call** (independent
  architecture assessment §5.2 / §3.4 point 5: "quota, budget,
  residency, and risk policies permit execution") — this is the
  rate-shaped reference implementation for the platform-wide
  quota-wiring gap; see Vector DB's README for the capacity-shaped
  counterpart (`vector_count`). `requests_per_minute` is a rate-shaped
  resource class in `QuotaEnforcementService`'s own terms (Module 30):
  Multi-tenancy owns the counter itself, so this module only needs to
  ask, before virtual-key budget reservation and before the semantic
  cache lookup — a denial there is still a denial from the requesting
  tenant's own quota perspective, not conditional on a cache miss. A
  denial raises `QuotaExceededError` → `429 Too Many Requests`, before
  any provider is called. `tokens_per_minute` is deliberately **not**
  wired here: it's also rate-shaped, but the actual token count for a
  request is unknown pre-flight (only after the provider responds),
  a genuinely different accounting design out of scope for this
  reference pass. `HTTPMultiTenancyClient`
  (`clients/multi_tenancy_client.py`) is a `ResilientHTTPClient` and
  **fails open** on any error — same posture as
  `EntitlementGateMiddleware` above: a Multi-tenancy outage must never
  itself block every completion this module serves. `multi_tenancy` is
  an optional constructor argument on `LLMGatewayService` — omitting it
  skips the check entirely, unchanged from before this fix.

- **Real OpenAPI contract testing** (`tests/contract/`) — this
  module's rollout of Billing and Metering's own Phase 1
  CI-supply-chain-gate reference implementation (ticket #73/#80):
  `schemathesis`/Hypothesis drive schema-conformant-but-otherwise-
  arbitrary requests at this module's real, running app (real
  middleware, real Postgres) for every operation its own generated
  OpenAPI document declares, and any `5xx` is a genuine contract
  violation. It found two real bugs on its first runs (a non-UUID
  `X-Virtual-Key`/budget-policy id reaching `asyncpg` unguarded on
  `get_virtual_key`/`get_budget_policy`, and an unbounded `offset` on
  `GET /admin/virtual-keys` overflowing Postgres's `bigint` column —
  both now fixed; see the module docstring in
  `tests/contract/test_openapi_contract.py` and `tests/contract/
  conftest.py` for the full account, including why this module's own
  real LLM provider/Multi-tenancy dependencies are swapped for the
  empty-providers default/a stub in the contract fixture, and the DB
  engine for a `NullPool` one). CI (`.github/workflows/ci.yml`) runs
  this tier automatically for any module with a `tests/contract/`
  directory.

- **Real admin provisioning for a `ProviderConfig`/`BudgetPolicy`**
  (ticket #82's own Phase 2 support-agent slice) — there was no way at
  all, through this module's own real API, to create either (only
  `update_provider_config`, requiring a pre-existing row, and no create
  route for a budget policy). Added `POST /admin/providers` and
  `POST /admin/budget-policies`, plus `repository.create_provider_config()`.

- **More of the same NUL-byte class, found once ticket #82's
  platform-wide sweep re-ran this module's own contract tier.** `GET
  /admin/virtual-keys`'s `tenant_id` never ran through a NUL-byte
  validator either — a plain, un-wrapped `str` function parameter
  rather than an explicit `Query()` default, which is why the sweep's
  initial grep for `Query(` missed this file; fixed with
  `_reject_null_byte_query()`. Re-running the contract tier after that
  fix surfaced a sibling body-field gap this module's earlier NUL-byte
  fix (above) hadn't covered: `POST /admin/providers`'s
  `provider_name`/`endpoint`, `POST /admin/virtual-keys`'s
  `tenant_id`/`budget_policy_ref`/`provider_scope`, and `POST
  /admin/budget-policies`'s `tenant_id` all reached the database raw;
  fixed with the same `_reject_null_byte` `field_validator` pattern
  Multi-tenancy's and Billing and Metering's own schemas already
  established. No route-level test file existed for `routes_admin.py`
  before this fix — `tests/unit/test_routes_admin.py` (new) pins these
  regressions; comprehensive route coverage remains a real,
  separately-scoped gap.

- **`anyio` 4.15.0 (released the day this was found) broke every
  contract-tier module's dev install.** It dropped/broke the
  `start_blocking_portal` lazy-import alias `starlette-testclient` 0.4.1
  depends on, so a fresh `uv pip install -e ".[dev]"` (this module's own
  pre-existing local `.venv`s, created before that release, were
  unaffected) started resolving the broken version and every contract
  test failed at import (`AttributeError: module 'anyio' has no
  attribute 'start_blocking_portal'`) rather than at any real assertion.
  Confirmed as upstream dependency drift unrelated to this repo's own
  history: identical failure on all seven contract-tier modules, on the
  base branch's own CI run, and PyPI's own release date for 4.15.0.
  Pinned `anyio<4.15` in `pyproject.toml`'s dev deps, resolving back to
  the known-good `4.14.2`.

- **The platform's own "unbounded integer" class recurred against a
  narrower Postgres range than `offset`'s.** Re-running this module's
  contract tier with the `anyio` pin in place (rather than failing at
  import) surfaced a real bug the tier had never gotten the chance to
  run against before: `POST /admin/providers`'s `priority` was a bare
  `int` — schema-valid per OpenAPI (`type: integer` says nothing about
  range) — but `ProviderConfigRecord.priority` is a Postgres `INTEGER`
  (int4, max `2_147_483_647`), so a value at or above `2**31` crashed
  with an unhandled `asyncpg.DataError` instead of a clean `422`. This
  is the identical unbounded-integer shape as the platform's `offset`
  class, but against int4's narrower range rather than `offset`'s int8
  one — the same grep-for-`Query(0, ge=0)` sweep would not have found
  it, since `priority` is a request body field, not a query parameter.
  `router.py`'s own routing score treats 0 as the best priority and
  divides by the largest priority present, so negative values are also
  nonsensical; bounded to `Field(ge=0, le=1_000_000)` — comfortably past
  any real ranking need, comfortably under the int4 overflow. The
  identical shape was found and fixed the same way in Multi-tenancy's
  `expected_version` (see that module's own README) while checking
  sibling modules for the same bug class.

## Running locally

```bash
uv venv && uv pip install -e ".[dev]"
pytest                                                    # unit tests, no external services needed

docker compose -f deploy/docker-compose.yml up --build    # full stack incl. Postgres, Redis, dependency-stub
```
