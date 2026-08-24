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
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI router — nodes, edges, query, neighbours shortcut
  schemas/                    Pydantic request/response models
```

## Design notes vs. the LLD

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

## Running locally

```bash
uv venv && uv pip install -e ".[dev]"
pytest                                                    # unit tests, no external services needed

docker compose -f deploy/docker-compose.yml up --build    # full stack incl. Postgres, dependency-stub
```
