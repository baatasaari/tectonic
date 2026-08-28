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
  clients/                 HTTP client for the LLM Gateway embeddings dependency
  security/                 Service-to-service JWT bearer auth (shared signing key), the entitlement gate
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI router — points, query, migrations
  schemas/                    Pydantic request/response models
```

Unlike every other module in this platform, there is **no `db/` or
`alembic/`** here: the LLD's own data model section is explicit that this
module's data model is "Qdrant collection schema, not a separate
relational model," and this build follows that literally — Qdrant (a
real `qdrant-client`, not a lightweight stand-in) is this module's only
persistence layer.

## Design notes vs. the LLD

- **Resiliency.** Every outbound HTTP call this module makes to a peer module goes through `ResilientHTTPClient` (`clients/resilience.py`): exponential-backoff retry on network errors and 5xx responses (never 4xx — a client error means the peer already processed the request and rejected it, so retrying just repeats the mistake), and a circuit breaker (`aiobreaker`) that opens after repeated failures so a struggling peer gets a break instead of a retry storm, and this module fails fast instead of piling up requests against a peer that's already down.

- **Qdrant itself: no deviation.** Unlike this platform's usual pattern
  of swapping a heavy/network-dependent LLD choice for a lightweight
  local stand-in, Qdrant's own Python client (`qdrant-client`) is used for
  real, because it's genuinely offline-testable: `AsyncQdrantClient(location=":memory:")`
  runs a real embedded Qdrant with no server process, exactly as the
  LLD's own testability contract calls for ("in-memory Qdrant mode for
  fast unit tests where available"). Production config
  (`vector_db.qdrant.url`) points the same client at a real cluster
  instead — no code changes.
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
- **Migration bookkeeping.** The LLD's data model table doesn't name a
  migration-tracking entity (consistent with "not a separate relational
  model"). `MigrationRecord` is the minimal state needed to serve `GET
  /migrations/{id}`; `core/fakes.py`'s `InMemoryMigrationRepository` is
  this module's only implementation today, so migration progress lives
  for the owning process's lifetime — acceptable given the LLD frames
  migrations as orchestrated by Workflow Engine, which already owns
  durable tracking for long-running background jobs.
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

## Running locally

```bash
uv venv && uv pip install -e ".[dev]"
pytest                                                    # unit tests, no external services needed — real embedded Qdrant

docker compose -f deploy/docker-compose.yml up --build    # full stack incl. a real Qdrant server, dependency-stub
```
