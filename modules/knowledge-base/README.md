# Knowledge Base / Document Management — Module 9

The system of record for unstructured source-of-truth content. Ingests
documents, chunks and versions them, applies access policy at chunk
level, and feeds Vector DB (embeddings) and Graph DB (entity extraction)
so Agentic RAG has something to retrieve. Owns document lifecycle; it
does not perform retrieval itself. Full design doc:
[`../../docs/module-09-knowledge-base.md`](../../docs/module-09-knowledge-base.md).

## Layout

```
src/knowledge_base/
  main.py                 FastAPI app, lifespan wiring, /healthz, /metrics
  app_context.py           Process-wide dependency container
  config.py                 Pydantic Settings — LLD config schema
  core/
    domain.py                Document/DocumentVersion/Chunk/PolicyTag dataclasses
    ports.py                   Repository, blob storage, Vector DB, Graph DB
    fakes.py                    In-memory implementations of every port, for unit tests
    parser.py                    Document Parser — text/Markdown/HTML extraction + heading detection
    chunker.py                    Chunking Engine — fixed_size, structural, semantic strategies
    similarity.py                  Term-frequency cosine similarity — the semantic chunker's coherence signal
    tokenization.py                 Local token-count estimator
    version_manager.py               Version Manager — content-addressed hashing
    policy_tagger.py                  Access Policy Tagger — chunk-level tag inheritance/override
    staleness_monitor.py               Staleness Monitor — threshold-based flagging + ratio
    ingestion_service.py                Ingestion Service — the orchestrator (this module's "scheduler")
  db/                      SQLAlchemy 2.0 async models + repository
  clients/                 HTTP clients for Vector DB/Graph DB + local blob storage adapter
  security/                 Service-to-service JWT bearer auth (shared signing key), the entitlement gate, real OpenAPI security scheme declarations
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI router — documents, versions, chunks, review
  schemas/                    Pydantic request/response models
```

## Design notes vs. the LLD

- **Resiliency.** Every outbound HTTP call this module makes to a peer module goes through `ResilientHTTPClient` (`clients/resilience.py`): exponential-backoff retry on network errors and 5xx responses (never 4xx — a client error means the peer already processed the request and rejected it, so retrying just repeats the mistake), and a circuit breaker (`aiobreaker`) that opens after repeated failures so a struggling peer gets a break instead of a retry storm, and this module fails fast instead of piling up requests against a peer that's already down.

- **Document parsing.** The LLD calls for `unstructured` and `pypdf` for
  multi-format parsing (PDF, DOCX, HTML, etc.). `core/parser.py`
  implements the text-native formats directly instead — plain text,
  Markdown (heading-aware via `#`-prefixed lines) and HTML (heading-aware
  via `<h1>`–`<h6>`, tags stripped for body text) — with a best-effort
  UTF-8/Latin-1 decode fallback for anything else, so the module has zero
  binary-parsing dependencies for its unit-test tier. Swapping in real
  PDF/DOCX support means implementing the same `parse()` interface with
  `unstructured`/`pypdf` behind it; every downstream stage (chunking,
  versioning, tagging) is unaffected by that choice.
- **Semantic chunking.** The LLD calls for "semantic (embedding-
  similarity-based)" chunking. `core/chunker.py`'s `chunk_semantic` reuses
  this platform's established lightweight fallback — term-frequency
  cosine similarity (`core/similarity.py`, the same approach Modules
  3/5/6 use) — as the coherence signal for where to break between
  sentences, instead of real sentence embeddings.
- **Object storage.** The LLD calls for an S3-compatible interface
  (AWS S3/GCS/Azure Blob). No cloud credentials are available in this
  build environment, so `clients/blob_storage.py`'s `FileBlobStorage`
  implements the same `BlobStorage` port against a local/mounted
  directory, content-addressed by the same SHA-256 hash the Version
  Manager already computes. Swapping in a real S3-compatible backend
  means implementing the same `put`/`get` interface.
- **Ingestion request shape.** The LLD's `POST /documents` accepts "file
  (multipart) or source_ref" — a source_ref would pull bytes from Data
  Source Plugins (Module 8) for sync-originated documents. That
  cross-module fetch is out of scope here; the router accepts either an
  uploaded `file` or an inline `content_text` form field as the byte
  source, and still records `source_ref`/`source_type` as metadata so the
  data model matches the LLD exactly.
- **Postgres integration tests** — the repository layer is now also
  tested against a real Postgres (`tests/integration/`, opt-in via
  `TECTONIC_TEST_POSTGRES_URL` or Docker+testcontainers), covering a
  genuine multi-row bulk insert (`create_chunks`) with distinct real
  UUID primary keys and per-row JSONB `policy_tags` round-tripping, and
  a multi-table filter (`list_chunks_by_policy_tag`) that must return
  only the intended chunks — things SQLite's unit-tier fakes can't
  reliably prove. See `tests/integration/conftest.py` for how the
  Postgres instance is obtained. This tier caught a real schema-drift
  bug: `Document.last_reviewed_at` was mapped without
  `DateTime(timezone=True)` even though the Alembic migration (and the
  domain default, `datetime.now(UTC)`) both assume a timestamptz
  column — invisible under SQLite, but asyncpg rejected every
  `create_document` call using the domain default against real
  Postgres. Fixed in `db/models.py`; the integration suite now has a
  dedicated regression test for it.

- **Connection pooling tuned to replica count.** SQLAlchemy's out-of-
  the-box defaults (`pool_size=5`, `max_overflow=10`) are the same
  regardless of how many pods are running — at this module's own
  `deploy/helm/knowledge-base/values.yaml` `autoscaling.maxReplicas: 20`,
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
- **Pagination on `GET /chunks`.** Added `limit`/`offset` query params
  (default 50, max 200) and a `ChunkListResponse` envelope
  (`items`/`total`/`limit`/`offset`) — this endpoint previously returned
  every matching chunk unbounded for both of its lookup modes
  (`document_version_id` and `policy_tag`+`tenant_id`). Ordered by
  `chunk_index` ascending (by `document_version_id` then `chunk_index`
  for the policy-tag lookup, which can span multiple versions). The
  policy-tag path filters chunk membership in Python after the
  version-scoped fetch, since JSON-array containment isn't filterable
  at the SQL level in a way that's portable between the JSONB (Postgres)
  and JSON (SQLite) column variants this module already uses — so it
  paginates the filtered, deterministically ordered in-memory list
  rather than pushing `LIMIT`/`OFFSET` into that query.

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
  `HTTPVectorDBClient` (audience `vector-db`) and `HTTPGraphDBClient`
  (audience `graph-db`) make — a token minted to call one peer is
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
  entitle), it calls Multi-tenancy's real `GET /tenants/{id}/gate?module=knowledge-base`,
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

docker compose -f deploy/docker-compose.yml up --build    # full stack incl. Postgres, dependency-stub
```
