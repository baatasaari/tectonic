# Data Source Plugins — Module 8

Owns connectivity to external data systems on behalf of the platform:
relational databases, SaaS APIs, file stores, data warehouses. Normalises
whatever it pulls into a common internal schema, detects and adapts to
source schema drift, scores its quality, and hands off to whichever
module needs it (typically Knowledge Base for document-shaped data, or
directly to an agent via Tool Orchestration for structured queries). Full
design doc:
[`../../docs/module-08-data-source-plugins.md`](../../docs/module-08-data-source-plugins.md).

## Layout

```
src/data_source_plugins/
  main.py                 FastAPI app, lifespan wiring, /healthz, /metrics
  app_context.py           Process-wide dependency container
  config.py                 Pydantic Settings — LLD config schema
  core/
    domain.py                ConnectorConfig/SchemaSnapshot/SyncRun/QualityScore/DriftIncident dataclasses
    ports.py                   Repository, source connector runtime, Secrets client
    fakes.py                    In-memory implementations of every port, for unit tests
    schema_drift.py               Schema Drift Detector — deepdiff-based comparison + classification
    normalizer.py                  Normaliser — type inference and coercion to a common schema
    quality_scorer.py               Data Quality Scorer — completeness/freshness/format-validity
    sync_service.py                  Sync Service — the sync-run orchestrator (this module's "scheduler")
  db/                      SQLAlchemy 2.0 async models + repository
  clients/                 HTTP clients for source extraction + Secrets and Credential Management
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI router — connectors, sync, query, quality, drift-incidents
  schemas/                    Pydantic request/response models
```

## Design notes vs. the LLD

- **Resiliency.** Every outbound HTTP call this module makes to a peer module goes through `ResilientHTTPClient` (`clients/resilience.py`): exponential-backoff retry on network errors and 5xx responses (never 4xx — a client error means the peer already processed the request and rejected it, so retrying just repeats the mistake), and a circuit breaker (`aiobreaker`) that opens after repeated failures so a struggling peer gets a break instead of a retry storm, and this module fails fast instead of piling up requests against a peer that's already down.

- **Connector runtime.** The LLD calls for building on Airbyte's open
  source connector catalogue (Airbyte Protocol / PyAirbyte). Airbyte's
  Python SDK and its 300+ connectors are a large, heavyweight dependency
  set unsuited to this module's offline unit-test tier and to a from-
  scratch build within this session. `clients/http_clients.py` implements
  `HTTPSourceConnectorRuntime` instead: a generic HTTP adapter behind the
  `SourceConnectorRuntime` port that POSTs `{source_type, connection_config,
  credentials, query}` to a connector-runtime endpoint and gets back
  `{records, schema}`. Swapping in real Airbyte connectors means
  implementing the same `SourceConnectorRuntime.extract()` interface —
  e.g. a wrapper that shells out to `airbyte-lib`/PyAirbyte per
  `source_type` and reshapes its output into `ExtractionResult`. Every
  sync/drift/quality-scoring code path downstream of extraction is fully
  real and independent of this choice.
- **Credential handling.** Delegated entirely to a `SecretsClient` port
  (per the LLD's "no credentials stored locally, ever"), with an HTTP
  adapter (`HTTPSecretsClient`) calling out to the Secrets and Credential
  Management module. This module never persists a `secrets_ref`'s
  resolved value.
- **Schema drift classification.** The LLD leaves "additive, breaking,
  type-widening" as illustrative fixture categories (§Level 4 "Testing").
  `core/schema_drift.py` implements this concretely: field removals are
  always `breaking`; new fields are `additive`; type changes are
  `type_widening` only for a fixed table of safe generalisations
  (int→number, int/number/bool→string) and `breaking` otherwise. Auto-
  adapt then follows `drift.auto_adapt_scope` exactly as configured.

## Running locally

```bash
uv venv && uv pip install -e ".[dev]"
pytest                                                    # unit tests, no external services needed

docker compose -f deploy/docker-compose.yml up --build    # full stack incl. Postgres, dependency-stub
```
