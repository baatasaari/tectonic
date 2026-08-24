# Regulatory and Compliance — Module 17

Maps a single, once-implemented control (e.g. "human oversight on
high-risk decisions") to the specific clauses it satisfies across every
regulatory framework a tenant has enabled, and generates
framework-formatted evidence packs on demand. This module does not
implement controls itself — it maps and evidences controls implemented
by other modules (Human Oversight, Guardrails, Sentinel Agents, Workflow
Engine). Full design doc:
[`../../docs/module-17-regulatory-compliance.md`](../../docs/module-17-regulatory-compliance.md).

## Layout

```
src/regulatory_compliance/
  main.py                 FastAPI app, lifespan wiring (seeds the default crosswalk table), /healthz, /metrics
  app_context.py           Process-wide dependency container
  config.py                 Pydantic Settings — LLD config schema
  core/
    domain.py                FrameworkProfile/ControlMapping/ControlImplementationEvent/EvidencePack dataclasses
    mapping_data.py            The bundled default crosswalk table — the "living regulatory feed" data
    ports.py                    Repository, Auditability
    fakes.py                     In-memory implementations of every port, for unit tests
    crosswalk_engine.py           Crosswalk Engine + Coverage Calculator
    regulatory_feed.py             Regulatory Feed Manager — publishes/deprecates mapping-table versions
    evidence_generator.py           Evidence Pack Generator — real PDF (fpdf2) or JSON output
  db/                      SQLAlchemy 2.0 async models + repository
  clients/                 HTTP client for Auditability
  security/                 Service-to-service JWT bearer auth (shared signing key)
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI router — framework-profiles, mappings, control-events, coverage, evidence-packs
  schemas/                    Pydantic request/response models
```

## Design notes vs. the LLD

- **Evidence pack PDF generation.** The LLD's "PDF (via the platform's
  own PDF generation approach)" is realised with `fpdf2` — a genuinely
  lightweight, pure-Python PDF writer with no system dependencies, so
  this is real PDF byte generation, not a text-file stand-in. `document_format:
  json` is also supported per the LLD's config (`evidence.output_format`).
- **Control events source.** The LLD's Level 2 diagram has Human
  Oversight/Guardrails/Workflow Engine publish control events to
  Auditability, which this module then queries. Auditability is Module
  20 and hasn't been built yet in this platform, so `POST
  /control-events` accepts direct ingestion from source modules instead
  — a drop-in swap for a real Auditability-event consumer once Module 20
  exists. `HTTPAuditabilityClient.query_control_events` still targets a
  plausible Auditability endpoint for best-effort evidence-pack
  enrichment; every call site treats a failure as "no enrichment
  available," never as a reason to fail generation, since this module's
  own `ControlImplementationEvent` rows remain the evidence source of
  record either way.
- **Async evidence generation.** Implemented as a real FastAPI
  `BackgroundTasks` job (not a queue/worker deployment) — `POST
  /evidence-packs` returns immediately with `status=generating`, and the
  background job opens its own DB session (the request-scoped one is
  already torn down by the time background tasks run) before flipping
  the record to `completed` or `failed`.
- **Crosswalk mapping table.** `core/mapping_data.py` ships a default
  crosswalk covering the controls this platform's other governance
  modules already implement (human oversight, guardrails policy checks,
  sentinel monitoring, audit logging, workflow confidence-gating, PII
  redaction, right-to-erasure) against EU AI Act, NIST AI RMF, ISO 42001,
  DORA **and GDPR**. GDPR was missing from the first cut of this table —
  a real gap, not a deliberate scoping decision, caught in review — and is
  now mapped against four controls this platform already implements:
  Long-Term Memory's provable right-to-erasure flow (Art.17), Guardrails'
  PII redaction (Art.5(1)(c), Art.25), Human Oversight's approval queue
  (Art.22, the automated-decision-making safeguard), and Auditability's
  event log (Art.30, Art.5(2)). `RegulatoryFeedManager`
  reads config-driven mapping data (this file today; `mapping_table_path`
  can point at an operator-supplied YAML file), matching the LLD's
  "living regulatory feed" claim that a new framework or delegated act is
  a data change, not a code change. `POST /mappings/publish` is the
  feed-update endpoint from LLD §Level 3's "regulatory feed update"
  sequence — it deprecates (never deletes) prior-version rows for the
  frameworks it touches, so a tenant pinned to an older
  `FrameworkProfile.version` is unaffected until they explicitly opt in
  to the newer version.
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
  *specific* peer being called on every outbound request this module's
  `HTTPAuditabilityClient` makes — a token minted to call one peer is
  rejected if replayed against a different one. The shared secret
  (`TECTONIC_JWT_SHARED_SECRET`, one Kubernetes Secret referenced by
  every module's Helm chart under this same literal env var name, not a
  per-module-prefixed one) defaults to an obviously-insecure placeholder
  for zero-config local dev/tests; `main.py` logs a startup warning if
  it's still active. This is service-to-service auth for inter-module
  calls, not the platform's external-facing user-auth story — a real API
  gateway/OAuth layer in front of the platform's own entry points is a
  separate, larger concern, out of scope here.

## Running locally

```bash
uv venv && uv pip install -e ".[dev]"
pytest                                                    # unit tests, no external services needed

docker compose -f deploy/docker-compose.yml up --build    # full stack incl. Postgres, dependency-stub
```
