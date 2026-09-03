# Vector DB — Module 10

Stores and retrieves embeddings for semantic search, on behalf of
Knowledge Base (document chunks) and any other module needing vector
similarity search. Owns the embedding generation step for content handed
to it (delegating the actual model call to LLM Gateway) and the
storage/query layer, backed by real Qdrant. Full design doc:
[`../../docs/module-10-vector-db.md`](../../docs/module-10-vector-db.md).

## Layout

```
src/vector_db/
  main.py                 FastAPI app, lifespan wiring, /healthz, /metrics
  app_context.py           Process-wide dependency container
  config.py                 Pydantic Settings — LLD config schema
  core/
    domain.py                MigrationRecord/ScoredPointResult/SparseVectorData dataclasses
    ports.py                   EmbeddingProvider, MigrationRepository — this module's only ports
    fakes.py                    In-memory implementations of those two ports, for unit tests
    qdrant_ops.py                 Alias resolution, collection bootstrap, payload filter builder
    sparse_encoder.py               Sparse Encoder — hashing-trick BM25-style sparse vectors
    vector_service.py                Vector Service — index/delete/query, hybrid fusion via Qdrant itself
    migration_manager.py              Migration Manager — zero-downtime re-embedding + alias cutover
  db/                       SQLAlchemy 2.0 async model + repository — migration bookkeeping only
  clients/                 HTTP client for the LLM Gateway embeddings dependency
  security/                 Service-to-service JWT bearer auth (shared signing key), the entitlement gate, real OpenAPI security scheme declarations
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI router — points, query, migrations
  schemas/                    Pydantic request/response models
alembic/                 DB migrations for the migrations table above (see "Migration bookkeeping" below)
```

The LLD's own data model section is explicit that this module's data
model is "Qdrant collection schema, not a separate relational model,"
and that's still true for the actual vector data: Qdrant (a real
`qdrant-client`, not a lightweight stand-in) is the only place a point
or embedding is ever stored. The one thing this module *does* keep in
Postgres — added for the independent architecture assessment's §10
fix, see "Migration bookkeeping" below — is its own migration-progress
bookkeeping, a genuinely separate relational concern from the vector
data plane itself.

## Design notes vs. the LLD

- **Resiliency.** Every outbound HTTP call this module makes to a peer module goes through `ResilientHTTPClient` (`clients/resilience.py`): exponential-backoff retry on network errors and 5xx responses (never 4xx — a client error means the peer already processed the request and rejected it, so retrying just repeats the mistake), and a circuit breaker (`aiobreaker`) that opens after repeated failures so a struggling peer gets a break instead of a retry storm, and this module fails fast instead of piling up requests against a peer that's already down.

- **Qdrant itself: no deviation, and no more silent in-memory
  production default** (independent architecture assessment §10, this
  module's highest-severity finding: "in-memory Qdrant is the
  default"). Unlike this platform's usual pattern of swapping a heavy/
  network-dependent LLD choice for a lightweight local stand-in,
  Qdrant's own Python client (`qdrant-client`) is used for real, because
  it's genuinely offline-testable: `AsyncQdrantClient(location=":memory:")`
  runs a real embedded Qdrant with no server process, exactly as the
  LLD's own testability contract calls for ("in-memory Qdrant mode for
  fast unit tests where available"). That was previously reachable from
  production too: `qdrant.url` defaulted to `None`, and `main.py` fell
  back to the in-memory client whenever it was falsy — a deployment
  that simply forgot to set the URL silently ran with zero persistence,
  losing every indexed point on the next restart, no warning logged.
  Fixed: `qdrant.url` now defaults to a real `http://localhost:6333`
  (the same "give a real local component a real localhost default"
  convention every other module's `database_url`/peer `base_url`
  fields already follow), and the in-memory client is reachable only
  through a new, explicit `qdrant.embedded_in_memory` flag — `main.py`
  logs a loud startup warning whenever it's true, the same posture
  `jwt_shared_secret`'s own insecure-default warning already takes.
  This module's own unit-test harness (`tests/conftest.py`) never reads
  either field at all — it constructs its own in-memory client directly
  — so this fix changes zero test behavior, only the previously-unsafe
  production default.
- **Sparse encoding.** The LLD calls for `fastembed`'s sparse models.
  `fastembed` downloads its models from Hugging Face Hub on first use — a
  network dependency this module's unit-test tier shouldn't carry.
  `core/sparse_encoder.py` implements a real BM25-style sparse vector via
  the hashing trick instead (each term hashed via `zlib.crc32` into a
  fixed-size index space, weighted by log-dampened term frequency) — a
  standard, well-understood technique needing no pretrained vocabulary.
  Swapping in `fastembed` means implementing the same `encode()`
  interface.
- **Zero-downtime migration mechanism.** Qdrant fixes a named vector's
  dimensionality at collection-creation time, so an in-place resize isn't
  possible when a new embedding model changes dimensionality.
  `VectorService` therefore never addresses a bare collection name —
  every read/write goes through a Qdrant *alias*. `MigrationManager`
  implements the LLD's shadow-write pattern using Qdrant's own
  recommended zero-downtime reindex approach: create a new physical
  collection sized for the new model, re-embed and shadow-write every
  point into it in batches (the old collection keeps serving live traffic
  throughout), spot-verify a sample, then atomically repoint the alias in
  one `update_collection_aliases` call, and finally prune the old
  collection.
- **Migration bookkeeping: now real, durable Postgres, not
  process-lifetime memory** (independent architecture assessment §10's
  other Vector DB finding: "migration state is in memory"). The LLD's
  data model table doesn't name a migration-tracking entity (consistent
  with "not a separate relational model" for the *vector* data), but
  this module's own production wiring used to construct
  `InMemoryMigrationRepository()` unconditionally in `main.py` —
  meaning a real in-flight migration's progress vanished on any
  restart, not just in tests. `db/repository.py`'s
  `SQLAlchemyMigrationRepository` replaces it, backed by a new
  `migrations` table (`alembic/versions/0001_initial.py`). It holds an
  `async_sessionmaker`, not a single shared `AsyncSession`, and opens a
  fresh session per method call — deliberately, since `AppContext`
  holds one long-lived instance of it, called both from request
  handlers *and* from the detached `asyncio.create_task` a migration
  run starts (`api/routes_vectors.py`), and a single shared session
  isn't safe under concurrent, unrelated callers. The same "safe to
  hold as a long-lived singleton, fresh session per operation" shape
  `OutboxRelayWorker`/`EvidencePackWorker` already use via their own
  `repository_factory` callables elsewhere in this platform, adapted
  here to a plain repository rather than a poll-loop worker. Verified
  against real Postgres (create/get/update round-trips, and 10
  concurrent callers never colliding) in
  `tests/integration/test_migration_repository_postgres.py`.
- **Point content in payload.** Re-embedding a point during migration
  needs its original text. The LLD's payload field list doesn't include
  raw content, so `payload.content` is stored alongside the fields the
  LLD does name (`tenant_id`, `source_module`, `source_ref`,
  `embedding_model_version`) — the minimal addition needed to make
  automatic migration actually operable without a synchronous round trip
  back to the owning module by `source_ref`.
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
  `HTTPEmbeddingProvider` makes — targeting LLM Gateway's
  OpenAI-compatible embeddings endpoint, so its audience is `llm-gateway`
  — a token minted to call one peer is rejected if replayed against a
  different one. The shared secret (`TECTONIC_JWT_SHARED_SECRET`, one
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
  entitle), it calls Multi-tenancy's real `GET /tenants/{id}/gate?module=vector-db`,
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
  /tenants/{id}/quota/check`, on every `index_point` call** (independent
  architecture assessment §5.2 / §3.4 point 5: "quota, budget,
  residency, and risk policies permit execution") — this is the
  capacity-shaped reference implementation for the platform-wide
  quota-wiring gap; see LLM Gateway's README for the rate-shaped
  counterpart (`requests_per_minute`). `vector_count` is a
  capacity-shaped resource class in `QuotaEnforcementService`'s own
  terms (Module 30): Multi-tenancy tracks no live usage for it, so this
  module — the real source of truth for how many points a tenant
  currently has indexed — supplies `current_usage` itself
  (`VectorService._current_vector_count`, a real `client.count(...)`
  against the tenant's own physical collection/filter, scoped the same
  way `query()` already scopes reads: by alias under
  `dedicated_collection` tenancy, by a `tenant_id` payload filter under
  `shared_collection_with_filter`). A denial raises `QuotaExceededError`
  → `429 Too Many Requests`, before any point is embedded or written.
  `HTTPMultiTenancyClient` (`clients/multi_tenancy_client.py`) is a
  `ResilientHTTPClient` and **fails open** on any error — same posture
  as `EntitlementGateMiddleware` above: a Multi-tenancy outage must
  never itself block every write this module makes. `multi_tenancy` is
  an optional constructor argument on `VectorService` — omitting it (as
  this module's own unit-test harness can, via `harness_factory()`)
  skips the check entirely, unchanged from before this fix.

- **`HTTPEmbeddingProvider` calling a real LLM Gateway for the first
  time** (ticket #82's own Phase 2 support-agent slice) — it posted to an
  invented `/v1/embeddings` path with no virtual-key/tenant headers; the
  real route is `/v1/llm-gateway/embeddings`, needing `X-Virtual-Key`/
  `X-Tenant-Id`. Fixed, with a new `llm_gateway_virtual_key` setting and
  `tenant_id` threaded through every `EmbeddingProvider.embed()` call
  site (`vector_service.py`, `migration_manager.py`) — invisible before
  because every prior test stubbed this call.

- **`anyio` 4.15.0 (released the day this was found) broke every
  contract-tier module's dev install.** It dropped/broke the
  `start_blocking_portal` lazy-import alias `starlette-testclient` 0.4.1
  depends on, so a fresh `uv pip install -e ".[dev]"` (this module's own
  pre-existing local `.venv`, created before that release, was
  unaffected) started resolving the broken version and every contract
  test failed at import (`AttributeError: module 'anyio' has no
  attribute 'start_blocking_portal'`) rather than at any real assertion.
  Confirmed as upstream dependency drift unrelated to this repo's own
  history: identical failure on all seven contract-tier modules, on the
  base branch's own CI run, and PyPI's own release date for 4.15.0.
  Pinned `anyio<4.15` in `pyproject.toml`'s dev deps, resolving back to
  the known-good `4.14.2`. (LLM Gateway's and Multi-tenancy's own
  READMEs document the same pin alongside a real bug it let their own
  contract tiers actually run against for the first time.)

## Running locally

```bash
uv venv && uv pip install -e ".[dev]"
pytest tests/unit                                                   # unit tests, no external services needed — real embedded Qdrant

docker compose -f deploy/docker-compose.yml up --build    # full stack incl. a real Qdrant server, Postgres, dependency-stub
```

## Testing tiers

| Tier | What it needs | How to run |
|---|---|---|
| Unit | Nothing — real embedded Qdrant, in-memory migration repository fake | `pytest tests/unit` |
| Integration | Real Postgres (`TECTONIC_TEST_POSTGRES_URL` or Docker via `testcontainers`) — migration bookkeeping only, Qdrant itself needs no real server at any tier | `pytest tests/integration` |
| Contract | Real Postgres (same as Integration); Qdrant still runs embedded in-memory | `pytest tests/contract` |

The contract tier (`tests/contract/`) is this platform's rollout of
Billing and Metering's own Phase 1 CI-supply-chain-gate reference
implementation (ticket #73/#80): `schemathesis`/Hypothesis drive
schema-conformant-but-otherwise-arbitrary requests at this module's
real, running app (real middleware, real Postgres, embedded Qdrant)
for every operation its own generated OpenAPI document declares, and
any `5xx` is a genuine contract violation. It found real bugs on its
first runs, most of them genuine gaps in this module's own dimension/
input handling rather than the familiar NUL-byte/non-UUID class alone:
a zero-dimensional or non-finite/overflowing `vector`, a dimension
mismatch between a request's `vector` and its tenant's already-
established collection (on both `index_point` and `query` — Qdrant's
own real API rejects this cleanly, but its embedded local test client
instead corrupts that collection's internal state, corrupting later
unrelated reads too), an empty or non-primitive `filters` value, a
non-positive `top_k`, and a non-UUID migration id — all now fixed; see
the module docstring in `tests/contract/test_openapi_contract.py` and
`tests/contract/conftest.py` for the full account, including why this
module's own real LLM Gateway/Multi-tenancy dependencies and its
detached migration-run background task are swapped for stubs/a no-op
and the DB engine for a `NullPool` one in the contract fixture. CI
(`.github/workflows/ci.yml`) runs this tier automatically for any
module with a `tests/contract/` directory.
