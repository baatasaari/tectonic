# Observability — Module 19

The platform-wide sink for every trace, span, metric and log emitted by
every other module in this platform. Every other module's own
`telemetry/tracing.py` assumes this module (or, in production, the real
OTel/Tempo/Grafana stack it's meant to front) is the destination. This
module's own differentiators are the Reasoning-Trace Reconstructor and
Cost Attribution Joiner. Full design doc:
[`../../docs/module-19-observability.md`](../../docs/module-19-observability.md).

## Layout

```
src/observability/
  main.py                 FastAPI app, lifespan wiring, /healthz, /metrics
  app_context.py           Process-wide dependency container
  config.py                 Pydantic Settings — LLD config schema
  core/
    domain.py                SpanRecord/CostAttributionEntry/TraceCompletenessResult dataclasses
    ports.py                    Repository, LLM Gateway
    fakes.py                      In-memory implementations of every port, for unit tests
    ingestion.py                    Ingestion Service — the OTLP-endpoint substitute (see its docstring)
    reasoning_reconstructor.py        Reasoning-Trace Reconstructor — LLM Gateway call + deterministic fallback
    cost_attribution.py                 Cost Attribution Joiner — reads LLM Gateway's real `gen_ai.usage.*`/`llm_gateway.cost` span attributes
    completeness.py                       Trace completeness vs configured expected workflow shapes
  db/                      SQLAlchemy 2.0 async model + repository
  clients/                 HTTP client for LLM Gateway (narrative generation)
  telemetry/                OTel tracing, Prometheus meta-metrics, structlog logging
  api/                       FastAPI router — ingest, reasoning-narrative, cost-attribution, trace-completeness
  schemas/                    Pydantic request/response models
```

## Design notes vs. the LLD

- **End-to-end distributed trace propagation — added after review, not a
  pre-existing feature.** Ingesting spans into one Postgres table isn't
  what makes tracing "end-to-end": until this fix, every module's
  outbound HTTP calls to a peer module carried no trace context, so
  `FastAPIInstrumentor` on the receiving side always started a *new* root
  trace — a request touching five modules produced five disconnected
  traces, not one. Every module's `main.py` now also calls
  `HTTPXClientInstrumentor().instrument()` alongside the existing
  `FastAPIInstrumentor.instrument_app(app)`, which is what actually closes
  the gap: it injects a W3C `traceparent` header into every outbound
  `httpx` call platform-wide (not just this module's own client), and
  `FastAPIInstrumentor` already extracts that header on the receiving
  side by default. Verified directly, not just installed: an isolated
  reproduction (one `httpx.AsyncClient` instrumented the same way, one
  downstream FastAPI app instrumented the same way, an
  `InMemorySpanExporter` capturing every span) shows the caller span, the
  httpx client span, and the downstream server span all carrying the
  identical `trace_id` — genuine cross-process trace continuity, not
  three separately-rooted traces that merely look related. This is a
  platform-wide fix (every one of the 19 modules built so far carries
  it), not something local to this module — Observability's own
  ingestion endpoint is a separate, still-real deviation (see below);
  what those spans look like *before* they reach this module's
  ingestion endpoint is what changed here.
- **The Grafana/Tempo/Mimir/Loki stack.** This is the one deviation that
  matters in this module: the LLD's storage/query layer is Grafana
  Tempo (traces), Mimir/Prometheus (metrics) and Loki (logs), fronted by
  an OpenTelemetry Collector's OTLP/gRPC ingestion endpoint — all real
  infrastructure components (Go binaries, Helm charts), not
  pip-installable Python packages, so they can't be stood up as part of
  this module's own lightweight, independently-testable build the way
  this platform's other named dependencies can. `core/ingestion.py`
  substitutes a simplified JSON HTTP endpoint (`POST
  /v1/observability/ingest`) storing spans in this module's own Postgres
  table. What this module actually differentiates on — the
  Reasoning-Trace Reconstructor and Cost Attribution Joiner — is real,
  tested code, run against that local store; only the underlying
  storage/query engine is substituted, matching the LLD's own
  testability contract wording almost verbatim ("tested with fixture
  trace data, independent of a live OTel pipeline"). Every other
  module's `telemetry/tracing.py` still exports real OTLP spans over
  gRPC; pointing that at a real Collector/Tempo stack instead of this
  module is a deployment-time config change, not a code change anywhere
  in this platform.
- **Cost attribution is real cross-module wiring, not a stub.** LLM
  Gateway (Module 3)'s own `telemetry/tracing.py` documents the exact
  attribute names its `gen_ai.client.chat` spans carry:
  `gen_ai.usage.input_tokens`/`output_tokens` (the standard OTel GenAI
  semantic convention) and its own `llm_gateway.cost` extension
  attribute. `core/cost_attribution.py` reads those exact keys — a
  genuine cross-module contract, not an invented shape.
- **Reasoning-trace fallback.** The LLD's narrative generation is a
  single LLM Gateway call. This module additionally falls back to a
  deterministic, span-name-ordered narrative when that call fails or
  `reasoning_narrative.enabled` is off — the same
  "LLM call for the common case, a documented lesser fallback for the
  degraded case" pattern used elsewhere in this platform (e.g.
  Guardrails' ambiguous-jailbreak fallback), rather than surfacing an
  error to a support engineer mid-incident.

- **Connection pooling tuned to replica count.** SQLAlchemy's out-of-
  the-box defaults (`pool_size=5`, `max_overflow=10`) are the same
  regardless of how many pods are running — at this module's own
  `deploy/helm/observability/values.yaml` `autoscaling.maxReplicas: 20`,
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
