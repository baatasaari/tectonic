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
  security/                 Service-to-service JWT bearer auth (shared signing key)
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI router — documents, versions, chunks, review
  schemas/                    Pydantic request/response models
```

## Design notes vs. the LLD

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

## Running locally

```bash
uv venv && uv pip install -e ".[dev]"
pytest                                                    # unit tests, no external services needed

docker compose -f deploy/docker-compose.yml up --build    # full stack incl. Postgres, dependency-stub
```
