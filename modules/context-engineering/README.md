# Context Engineering — Module 7

The final assembly step before a prompt goes to LLM Gateway: takes
candidate context (from Agentic RAG, Short-Term Memory, Long-Term Memory,
Workflow context) and shapes it into the actual prompt context within a
token budget, prioritising what matters most for the specific task. Does
not retrieve content itself — consumes retrieved candidates and decides
what survives into the final prompt. Full design doc:
[`../../docs/module-07-context-engineering.md`](../../docs/module-07-context-engineering.md).

## Layout

```
src/context_engineering/
  main.py                 FastAPI app, lifespan wiring, /healthz, /metrics
  app_context.py           Process-wide dependency container
  config.py                 Pydantic Settings — LLD config schema
  core/
    domain.py                CandidateItem/TaggedItem/RankedItem/AssembledItem dataclasses
    ports.py                   Repository, LLM Gateway (summarisation), Evaluation Framework feedback
    fakes.py                    In-memory implementations of every port, for unit tests
    tokenization.py               Token counting — whitespace-based estimate, no tiktoken network fetch
    ontology_filter.py             Ontology Filter — tags + excludes ungoverned policy tags
    prioritisation_engine.py        Prioritisation Engine — feature-weighted, explainable scoring
    token_budget_enforcer.py         Token Budget Enforcer — greedy knapsack selection
    compression.py                    Compression/Summarisation — LLM Gateway call, used sparingly
    context_assembly_service.py        The assembly orchestrator (this module's "scheduler")
  db/                      SQLAlchemy 2.0 async models + repository
  clients/                 HTTP clients for LLM Gateway and the Evaluation Framework feedback feed
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI routers — assemble, ontologies, weights
  schemas/                    Pydantic request/response models
```

## Design notes vs. the LLD

- **Resiliency.** Every outbound HTTP call this module makes to a peer module goes through `ResilientHTTPClient` (`clients/resilience.py`): exponential-backoff retry on network errors and 5xx responses (never 4xx — a client error means the peer already processed the request and rejected it, so retrying just repeats the mistake), and a circuit breaker (`aiobreaker`) that opens after repeated failures so a struggling peer gets a break instead of a retry storm, and this module fails fast instead of piling up requests against a peer that's already down.

- **Tokenisation.** The LLD names `tiktoken`. `core/tokenization.py`
  implements a whitespace/word-count-based estimator instead —
  `tiktoken`'s encodings are fetched from a remote blob store on first use
  and cached, a network dependency this module's tests shouldn't carry.
  Close enough for budget *enforcement* (this module's actual job); swap in
  `tiktoken` — or the model-specific tokenizer LLM Gateway's routing
  decision implies — by implementing the same `TokenCounter` interface.
- **Prioritisation Engine.** Feature-weighted scoring over a small,
  explainable feature set (role match, entity-type match, policy-tag match
  count, source identity) rather than a full ML pipeline, per the LLD's own
  stated rationale: "keeps this explainable and tunable rather than an
  opaque black box." `update_from_feedback` nudges weights by a bounded
  step per Evaluation Framework signal rather than overwriting them
  outright.
- **Ontology Filter as a real filter, not just tags.** An item whose
  metadata declares a `policy_tags` entry the tenant's ontology doesn't
  recognise is excluded outright, not merely left untagged — ungoverned
  content shouldn't silently reach the prompt.
- **Postgres integration tests** — the repository layer is now also tested
  against a real Postgres (`tests/integration/`, opt-in via
  `TECTONIC_TEST_POSTGRES_URL` or Docker+testcontainers), covering JSONB
  list/dict round-tripping (`OntologyConfig`, `PrioritisationWeights.
  feature_weights`), an upsert that updates rather than duplicates a row, and
  nested JSONB assembly logs with real UUID primary keys — all things SQLite's
  unit-tier fakes can't reliably prove. See `tests/integration/conftest.py`
  for how the Postgres instance is obtained. This tier's presence prompted a
  platform-wide sweep of every module's `db/models.py` for the same class of
  bug: `Mapped[datetime]` columns missing `DateTime(timezone=True)` despite
  the Alembic migration already defining them as timestamptz and the domain
  layer's defaults being tz-aware — invisible under SQLite, but a real
  correctness bug against Postgres once a domain default (or an explicit
  value) is written. Found and fixed here too.

## Running locally

```bash
uv venv && uv pip install -e ".[dev]"
pytest                                                    # unit tests, no external services needed

docker compose -f deploy/docker-compose.yml up --build    # full stack incl. Postgres, dependency-stub
```
