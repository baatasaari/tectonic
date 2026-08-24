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
  security/                 Service-to-service JWT bearer auth (shared signing key)
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
  *specific* peer being called on every outbound request `HTTPLLMGatewayClient`
  makes — a token minted to call one peer is rejected if replayed against
  a different one. The shared secret (`TECTONIC_JWT_SHARED_SECRET`, one
  Kubernetes Secret referenced by every module's Helm chart under this
  same literal env var name, not a per-module-prefixed one) defaults to
  an obviously-insecure placeholder for zero-config local dev/tests;
  `main.py` logs a startup warning if it's still active. This is
  service-to-service auth for inter-module calls, not the platform's
  external-facing user-auth story — a real API gateway/OAuth layer in
  front of the platform's own entry points is a separate, larger
  concern, out of scope here.

## Running locally

```bash
uv venv && uv pip install -e ".[dev]"
pytest                                                    # unit tests, no external services needed

docker compose -f deploy/docker-compose.yml up --build    # full stack incl. Postgres, dependency-stub
```
