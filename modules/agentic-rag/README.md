# Agentic RAG — Module 6

Given a query and a scope of source material, retrieves the most relevant,
groundable context for an LLM to reason over, iterating on its own
retrieval when the first pass is insufficient. Does not generate the final
answer — hands synthesized context to the calling module (typically
Conversational Engine or Workflow Engine), which then calls LLM Gateway for
generation. Full design doc:
[`../../docs/module-06-agentic-rag.md`](../../docs/module-06-agentic-rag.md).

## Layout

```
src/agentic_rag/
  main.py                 FastAPI app, lifespan wiring, /healthz, /metrics
  app_context.py           Process-wide dependency container
  config.py                 Pydantic Settings — LLD config schema
  core/
    domain.py                RetrievalRequest/Hop/Result, RetrievedItem, Provenance dataclasses
    ports.py                   Repository, Vector DB/Graph DB/Knowledge Base, LLM Gateway
    fakes.py                    In-memory implementations of every port, for unit tests
    similarity.py                 Term-frequency cosine similarity — the Heuristic Critic's scorer
    hybrid_retriever.py            Hybrid Retriever — fan-out + reciprocal rank fusion
    groundedness_critic.py          Groundedness Critic — LLM-backed or heuristic
    query_reformulator.py            Query Reformulator
    retrieval_loop.py                 Retrieve-Critique-Reformulate Loop (this module's "scheduler")
    rag_service.py                     Persists the loop's request/hops/result
  db/                      SQLAlchemy 2.0 async models + repository
  clients/                 HTTP clients for Vector DB / Graph DB / Knowledge Base / LLM Gateway
  security/                 Service-to-service JWT bearer auth (shared signing key)
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI routers — retrieve, request detail
  schemas/                    Pydantic request/response models
```

## Design notes vs. the LLD

- **Retrieve-Critique-Reformulate Loop.** The LLD assigns this to an ADK
  2.0 Workflow Runtime loop node. `core/retrieval_loop.py` implements the
  same termination semantics (groundedness threshold met, or max
  iterations reached) as a bounded async loop instead — same "behind a
  port, ADK is a pluggable production choice" boundary Module 1 draws
  around its own scheduler.
- **Hybrid Retriever.** Fans out to Vector DB, Graph DB and Knowledge Base
  concurrently and merges with reciprocal rank fusion — combining an
  approximate (vector) and an exact (symbolic) source on raw scores would
  let one backend's score scale dominate; RRF fuses on rank instead.
- **Groundedness Critic.** The LLD's `method: llm | dedicated_nli_model`
  config selects between `LLMGroundednessCritic` (an LLM Gateway call) and
  `HeuristicGroundednessCritic` — a term-overlap scorer standing in for a
  real NLI model, the same "no external model-serving dependency" move
  Module 5 makes for its primary classifier.
- **"Best hop" fallback.** Even when `max_hops_reached` without ever
  clearing the groundedness threshold, the result returned is the
  best-scoring hop seen, not the last one tried — a partial answer with
  provenance beats silently returning the weakest attempt.
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
  *specific* peer being called on every outbound request each of
  `HTTPVectorDBClient`, `HTTPGraphDBClient`, `HTTPKnowledgeBaseClient` and
  `HTTPLLMGatewayClient` makes — a token minted to call one peer is
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
