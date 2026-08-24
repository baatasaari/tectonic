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

- **Connection pooling tuned to replica count.** SQLAlchemy's out-of-
  the-box defaults (`pool_size=5`, `max_overflow=10`) are the same
  regardless of how many pods are running — at this module's own
  `deploy/helm/data-source-plugins/values.yaml` `autoscaling.maxReplicas: 20`,
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
