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

## Running locally

```bash
uv venv && uv pip install -e ".[dev]"
pytest                                                    # unit tests, no external services needed

docker compose -f deploy/docker-compose.yml up --build    # full stack incl. Postgres, dependency-stub
```
