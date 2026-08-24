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
  security/                 Service-to-service JWT bearer auth (shared signing key)
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI router — items, query, reflections, erasure-requests, consolidation-runs
  schemas/                    Pydantic request/response models
```

## Design notes vs. the LLD

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

## Running locally

```bash
uv venv && uv pip install -e ".[dev]"
pytest                                                    # unit tests, no external services needed

docker compose -f deploy/docker-compose.yml up --build    # full stack incl. Postgres, dependency-stub
```
