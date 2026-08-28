# Long-Term Memory — Module 13

The durable, cross-session memory store for facts, episodes, semantic
knowledge and procedural learning. Distinct from Short-Term Memory
(session-scoped, ephemeral); this module persists what an agent or user
relationship should remember across sessions, and owns the
consolidation, forgetting and self-reflection loops that let agents
genuinely improve over time. Full design doc:
[`../../docs/module-13-long-term-memory.md`](../../docs/module-13-long-term-memory.md).

## Layout

```
src/long_term_memory/
  main.py                 FastAPI app, lifespan wiring, /healthz, /metrics
  app_context.py           Process-wide dependency container
  config.py                 Pydantic Settings — LLD config schema
  core/
    domain.py                MemoryItem/ConsolidationRun/ReflectionEntry/DeletionRecord dataclasses
    ports.py                   Repository, Vector DB, Graph DB, LLM Gateway, Guardrails
    fakes.py                    In-memory implementations of every port, for unit tests
    memory_service.py             Mem0-based Memory Manager — store + retrieval fan-out
    visibility.py                  Cross-Agent Visibility Policy
    consolidation.py                Consolidation Engine — dedup + decay
    forgetting.py                    Forgetting Engine — verifiable cross-store deletion
    reflection.py                     Reflection Loop
  db/                      SQLAlchemy 2.0 async models + repository (this module's own facts/episodes/reflections/deletion records)
  clients/                 HTTP clients for Vector DB (Module 10), Graph DB (Module 11), LLM Gateway, Guardrails
  security/                 Service-to-service JWT bearer auth (shared signing key), the entitlement gate, real OpenAPI security scheme declarations
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI router — items, query, reflections, erasure-requests, consolidation-runs
  schemas/                    Pydantic request/response models
```

## Design notes vs. the LLD

- **Resiliency.** Every outbound HTTP call this module makes to a peer module goes through `ResilientHTTPClient` (`clients/resilience.py`): exponential-backoff retry on network errors and 5xx responses (never 4xx — a client error means the peer already processed the request and rejected it, so retrying just repeats the mistake), and a circuit breaker (`aiobreaker`) that opens after repeated failures so a struggling peer gets a break instead of a retry storm, and this module fails fast instead of piling up requests against a peer that's already down.

- **Memory framework.** The LLD calls for Mem0 (open source) as the base
  memory management layer. Mem0 pulls in its own embedding/vector-store
  backend choices and network-dependent defaults that don't fit this
  module's offline unit-test tier cleanly. `core/memory_service.py`
  implements the same shape directly instead — item CRUD, and retrieval
  fan-out across Postgres (fact/episodic), Vector DB (semantic, via
  Module 10) and Graph DB (procedural, via Module 11) — behind the same
  ports a real Mem0 integration would sit behind.
- **Reflection Loop.** The LLD calls for the ADK 2.0 `Agent` reflection
  pattern. `core/reflection.py` implements the same generate-and-store
  shape directly: one LLM Gateway call producing reflection content,
  persisted as a `ReflectionEntry`. Swapping in real ADK reflection
  primitives means implementing the same `generate()` interface.
- **API additions beyond the LLD's table.** `POST /reflections` and
  `POST /consolidation-runs` aren't in the LLD's documented API surface
  — the LLD frames reflections as triggered by Evaluation Framework
  (not yet a built module) and consolidation as a scheduled job (not yet
  wired to Workflow Engine). Both are exposed directly so this module is
  fully exercisable via HTTP today; once those integrations exist, these
  become internal calls this module receives from them rather than a
  public surface.
- **Graph DB erasure gap.** The LLD's "verifiable right-to-erasure"
  sequence calls for `FORGET->>GDB: DELETE nodes/edges with matching
  source_ref`, but Module 11 (Graph DB)'s own LLD and API surface don't
  define a delete endpoint yet. `HTTPGraphDBClient.delete_by_source_ref`
  calls a plausible `DELETE /v1/graph-db/nodes` and treats a failure as
  best-effort (logged, not raised) rather than failing the whole erasure
  — meaning today's erasure completes and produces a valid deletion
  proof for Postgres and Vector DB, but procedural (Graph DB) data tied
  to a forgotten subject may not actually be purged until Module 11 adds
  that endpoint. This is a real compliance gap worth flagging rather
  than silently declaring erasure complete for data this module can't
  yet prove it removed — see `ForgettingEngine`'s docstring.
- **Vector DB / Graph DB clients target the real modules.** Unlike some
  other cross-module HTTP clients in this platform that call invented
  endpoints because the peer module didn't exist yet, `HTTPVectorDBClient`
  and `HTTPGraphDBClient` call Module 10's and Module 11's actual,
  already-built API surfaces.
- **Postgres integration tests.** The repository layer is now also tested
  against a real Postgres (`tests/integration/`, opt-in via
  `TECTONIC_TEST_POSTGRES_URL` or Docker+testcontainers), covering
  `DeletionRecord.memory_items_deleted` JSONB round-tripping, a real UUID
  primary key round trip through create + update on `MemoryItem`, and a
  multi-row filtered query (`list_active` scoped by memory type) — none of
  which SQLite's unit-tier fakes can reliably prove. See
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
  `deploy/helm/long-term-memory/values.yaml` `autoscaling.maxReplicas: 20`,
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
- **Pagination on `GET /reflections`.** Added `limit`/`offset` query
  params (default 50, max 200) and a `ReflectionEntryListResponse`
  envelope (`items`/`total`/`limit`/`offset`) — reflections accumulate
  per agent over time and this endpoint previously returned every
  matching row unbounded. Ordered by `created_at` descending (newest
  reflection first).
- **`POST /query` deliberately left unpaginated.** This is a
  ranked-results endpoint, not a listing endpoint: `QueryRequest.top_k`
  (default 10) already caps the response the same way limit/offset
  would bound a list — `MemoryService.query` ranks all candidate matches
  by relevance and slices to `results[:top_k]` before returning. There's
  no "next page" of lower-ranked results a client would legitimately
  page through; a client wanting more results re-queries with a larger
  `top_k`. See the comment at the route in `api/routes_memory.py`.

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
  `HTTPVectorDBClient`, `HTTPGraphDBClient`, `HTTPLLMGatewayClient` and
  `HTTPGuardrailsClient` make — a token minted to call one peer is
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
  entitle), it calls Multi-tenancy's real `GET /tenants/{id}/gate?module=long-term-memory`,
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
