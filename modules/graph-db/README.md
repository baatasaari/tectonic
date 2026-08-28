# Graph DB — Module 11

Stores entities and their relationships for graph-based reasoning and
memory, on behalf of Agentic RAG (structured relationship retrieval),
Long-Term Memory (semantic/episodic graph) and Knowledge Base (entity
extraction from documents). Owns graph storage and query execution; it
does not decide what to extract or when to query. Full design doc:
[`../../docs/module-11-graph-db.md`](../../docs/module-11-graph-db.md).

## Layout

```
src/graph_db/
  main.py                 FastAPI app, lifespan wiring, /healthz, /metrics
  app_context.py           Process-wide dependency container
  config.py                 Pydantic Settings — LLD config schema
  core/
    domain.py                Node/Edge dataclasses, EdgeKind
    ports.py                   Repository, Auditability client
    fakes.py                    In-memory implementations of every port, for unit tests
    temporal.py                  Temporal Filter — valid_from/valid_to point-in-time predicate
    causal_validator.py           Causal Edge Validator — rejects untyped edges
    graph_engine.py                 Write Coordinator + Query Engine — BFS neighbours/path traversal
  db/                      SQLAlchemy 2.0 async models + repository
  clients/                 HTTP client for the Auditability dependency
  security/                 Service-to-service JWT bearer auth (shared signing key), the entitlement gate, real OpenAPI security scheme declarations
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI router — nodes, edges, query, neighbours shortcut
  schemas/                    Pydantic request/response models
```

## Design notes vs. the LLD

- **Resiliency.** Every outbound HTTP call this module makes to a peer module goes through `ResilientHTTPClient` (`clients/resilience.py`): exponential-backoff retry on network errors and 5xx responses (never 4xx — a client error means the peer already processed the request and rejected it, so retrying just repeats the mistake), and a circuit breaker (`aiobreaker`) that opens after repeated failures so a struggling peer gets a break instead of a retry storm, and this module fails fast instead of piling up requests against a peer that's already down.

- **Graph database.** The LLD calls for Neo4j or Memgraph via Cypher.
  Neither is installable/runnable in this build environment (no Docker
  for `testcontainers`, no external graph-DB service). `db/models.py`
  implements the same logical graph schema (nodes, edges with
  `valid_from`/`valid_to`/`edge_kind`/`confidence`/`source_ref`) as a
  relational table pair via the platform's established SQLAlchemy 2.0
  async pattern instead, so the module still gets real persistence
  (Postgres in production, SQLite for fast unit tests) without a Cypher
  engine. Traversal (`neighbours`, `path`) is implemented as bounded
  breadth-first search in Python over `list_outgoing_edges`/
  `list_incoming_edges` rather than pushed into a Cypher query — this is
  slower at very large graph scale than a native graph engine's index-
  free adjacency, but is correct and fully testable offline. Swapping in
  real Neo4j/Memgraph means implementing `GraphRepository` against the
  Cypher driver; `GraphEngine`'s traversal logic would then move into
  Cypher `MATCH` patterns instead.
- **Query surface.** The LLD itself defaults `raw_cypher_enabled: false`
  and recommends a "structured query DSL...to avoid raw Cypher injection
  risk" as the primary interface for calling modules. This build
  implements exactly that structured DSL (`query_type: "neighbours" |
  "path"`) and nothing else — raw Cypher stays out of scope, consistent
  with the LLD's own default-off posture, not a deviation from it.
- **Postgres integration tests.** The repository layer is now also tested
  against a real Postgres (`tests/integration/`, opt-in via
  `TECTONIC_TEST_POSTGRES_URL` or Docker+testcontainers), covering
  `Node.attributes` JSONB round-tripping, a real UUID primary/foreign key
  relationship between two nodes and the edge connecting them, and a
  tenant-scoped multi-row aggregation (`count_edges_by_kind`) — none of which
  SQLite's unit-tier fakes can reliably prove. See
  `tests/integration/conftest.py` for how the Postgres instance is obtained.
  This tier's presence prompted a platform-wide sweep of every module's
  `db/models.py` for the same class of bug: `Mapped[datetime]` columns missing
  `DateTime(timezone=True)` despite the Alembic migration already defining
  them as timestamptz and the domain layer's defaults being tz-aware —
  invisible under SQLite, but a real correctness bug against Postgres once a
  domain default (or an explicit value) is written. Found and fixed here too.

- **Connection pooling tuned to replica count.** SQLAlchemy's out-of-
  the-box defaults (`pool_size=5`, `max_overflow=10`) are the same
  regardless of how many pods are running — at this module's own
  `deploy/helm/graph-db/values.yaml` `autoscaling.maxReplicas: 20`,
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
  `HTTPAuditabilityClient` makes (audience `auditability`, Module 20)
  — a token minted to call one peer is rejected
  if replayed against a different one. The shared secret
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
  entitle), it calls Multi-tenancy's real `GET /tenants/{id}/gate?module=graph-db`,
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
