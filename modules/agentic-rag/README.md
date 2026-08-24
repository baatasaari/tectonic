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
- **Postgres integration tests** — the repository layer is now also tested
  against a real Postgres (`tests/integration/`, opt-in via
  `TECTONIC_TEST_POSTGRES_URL` or Docker+testcontainers), covering nested
  JSONB round-tripping of `retrieved_items`/`provenance_chain` and real UUID
  primary keys that SQLite's unit-tier fakes can't reliably prove. See
  `tests/integration/conftest.py` for how the Postgres instance is obtained.
  This tier's presence prompted a platform-wide sweep of every module's
  `db/models.py` for the same class of bug: `Mapped[datetime]` columns missing
  `DateTime(timezone=True)` despite the Alembic migration already defining
  them as timestamptz and the domain layer's defaults being tz-aware —
  invisible under SQLite, but a real correctness bug against Postgres once a
  domain default (or an explicit value) is written. Found and fixed here too.

## Running locally

```bash
uv venv && uv pip install -e ".[dev]"
pytest                                                    # unit tests, no external services needed

docker compose -f deploy/docker-compose.yml up --build    # full stack incl. Postgres, dependency-stub
```
