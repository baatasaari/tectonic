# Intent Detection — Module 5

The first classification step in most conversational and workflow paths:
given raw input and context, determines what the user is actually trying
to do, so the Conversational Engine or Workflow Engine can route
correctly. Classifies and hands off — it does not generate responses or
execute actions. Full design doc:
[`../../docs/module-05-intent-detection.md`](../../docs/module-05-intent-detection.md).

## Layout

```
src/intent_detection/
  main.py                 FastAPI app, lifespan wiring, /healthz, /metrics
  app_context.py           Process-wide dependency container
  config.py                 Pydantic Settings — LLD config schema
  core/
    domain.py                IntentTaxonomy/ClassificationLog/DriftReport dataclasses
    ports.py                   Repository, LLM Gateway fallback client
    fakes.py                    In-memory implementations of every port, for unit tests
    similarity.py                 Term-frequency cosine similarity — the Primary Classifier's scorer
    primary_classifier.py          Primary Classifier — fast single-pass scoring against the taxonomy
    compositional_decomposer.py     Compositional Decomposer — multi-intent signal detection
    llm_fallback.py                  LLM Fallback Handler
    drift_monitor.py                  Drift Monitor — Population Stability Index
    classification_service.py         The classification orchestrator (this module's "scheduler")
  db/                      SQLAlchemy 2.0 async models + repository
  clients/                 HTTP client for the LLM Gateway fallback dependency
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI routers — classify, taxonomies, drift-reports
  schemas/                    Pydantic request/response models
```

## Design notes vs. the LLD

- **Resiliency.** Every outbound HTTP call this module makes to a peer module goes through `ResilientHTTPClient` (`clients/resilience.py`): exponential-backoff retry on network errors and 5xx responses (never 4xx — a client error means the peer already processed the request and rejected it, so retrying just repeats the mistake), and a circuit breaker (`aiobreaker`) that opens after repeated failures so a struggling peer gets a break instead of a retry storm, and this module fails fast instead of piling up requests against a peer that's already down.

- **Primary Classifier.** The LLD calls for "a fine-tuned small model (e.g.
  a distilled transformer classifier)." `core/primary_classifier.py` scores
  each taxonomy intent by its closest labelled example via term-frequency
  cosine similarity (`core/similarity.py`) instead — a genuine local
  classifier with no external model-serving dependency, so unit and
  integration tests never depend on bundled model weights. Swapping in a
  real fine-tuned model means implementing the same `classify` interface.
- **Drift Monitor.** Implements Population Stability Index directly (one
  formula, not worth a stats library dependency) comparing the observed
  distribution of detected intents against a baseline approximated from
  each intent's labelled-example share — this module has no separate
  "training set" artifact to compare against.
- **Privacy by design.** Raw input text is never persisted — only
  `hash_input()`'s SHA-256 hash, per the LLD's `ClassificationLog.input_hash`
  field and its stated rationale.
- **Postgres integration tests** — the repository layer is now also tested
  against a real Postgres (`tests/integration/`, opt-in via
  `TECTONIC_TEST_POSTGRES_URL` or Docker+testcontainers), covering
  `IntentTaxonomy.intents` / `ClassificationLog.intents_detected` JSONB
  round-tripping (nested lists-of-dicts, exact float confidence values), a
  real UUID primary key, and a multi-row `get_taxonomy_by_version`/
  `get_active_taxonomy` query that must select only the intended
  tenant+version/status row among several taxonomies — all things SQLite's
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
