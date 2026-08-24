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

- **Connection pooling tuned to replica count.** SQLAlchemy's out-of-
  the-box defaults (`pool_size=5`, `max_overflow=10`) are the same
  regardless of how many pods are running — at this module's own
  `deploy/helm/intent-detection/values.yaml` `autoscaling.maxReplicas: 20`,
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
- **Pagination on `GET /drift-reports`.** Added `limit`/`offset` query
  params (default 50, max 200) and a `DriftReportListResponse` envelope
  (`items`/`total`/`limit`/`offset`) — this endpoint previously returned
  every matching row unbounded, and drift reports accumulate per tenant
  over the life of a taxonomy. Ordered by `created_at` descending
  (newest report first).

## Running locally

```bash
uv venv && uv pip install -e ".[dev]"
pytest                                                    # unit tests, no external services needed

docker compose -f deploy/docker-compose.yml up --build    # full stack incl. Postgres, dependency-stub
```
