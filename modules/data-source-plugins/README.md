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
- **Postgres integration tests** — the repository layer is now also tested
  against a real Postgres (`tests/integration/`, opt-in via
  `TECTONIC_TEST_POSTGRES_URL` or Docker+testcontainers), covering JSONB
  round-tripping of `connection_config`/`schema_diff`, real UUID primary keys,
  and a multi-row `list_sync_runs` query that must hit only the intended
  connector's rows — things SQLite's unit-tier fakes can't reliably prove. See
  `tests/integration/conftest.py` for how the Postgres instance is obtained.
  This tier's presence prompted a platform-wide sweep of every module's
  `db/models.py` for the same class of bug: `Mapped[datetime]` columns missing
  `DateTime(timezone=True)` despite the Alembic migration already defining
  them as timestamptz and the domain layer's defaults being tz-aware —
  invisible under SQLite, but a real correctness bug against Postgres once a
  domain default (or an explicit value) is written. Found and fixed here too.

- **Pagination on `GET /connectors/{connector_id}/drift-incidents`.**
  Added `limit`/`offset` query params (default 50, max 200) and a
  `DriftIncidentListResponse` envelope (`items`/`total`/`limit`/`offset`)
  — this endpoint previously returned every drift incident ever recorded
  for a connector unbounded, a real scaling gap for a long-lived
  connector with a large drift history. Ordered by `created_at`
  descending (newest incident first) for stable pagination.

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
