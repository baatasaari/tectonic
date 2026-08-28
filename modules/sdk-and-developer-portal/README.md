# SDK and Developer Portal — Module 34

The platform's developer-facing front door: register a developer,
provision them a real sandbox (a real Identity and Access identity, a
real Multi-tenancy tenant with `tier="sandbox"`), generate a working
client SDK from a real peer module's live OpenAPI spec, and report
adoption metrics computed from real Auditability history — not
self-reported. Full design doc: [`../../docs/module-34-sdk-and-developer-portal.md`](../../docs/module-34-sdk-and-developer-portal.md).

## Layout

```
src/sdk_and_developer_portal/
  main.py                 FastAPI app, lifespan wiring, /healthz, /metrics
  app_context.py           Process-wide dependency container
  config.py                  Pydantic Settings — LLD config schema
  core/
    domain.py                 DeveloperAccountRecord/ModuleCatalogEntryRecord/SdkPackageRecord, the developer lifecycle state machine
    sdk_codegen.py               Pure OpenAPI-spec-to-Python-client generator — no I/O, no fake needed
    ports.py                       Repository, the four real platform-peer client ports
    fakes.py                         In-memory implementations of every port, for unit tests
    developer_account_service.py       Developer Account Service — register/revoke, sandbox token issuance
    module_catalog_service.py            Module Catalog Service — syncs every peer's real OpenAPI spec
    sdk_generator_service.py               SDK Generator Service — spec-hash-keyed idempotent generation
    adoption_metrics_service.py              Adoption Metrics Service — real time-to-first-call, adoption rate
  db/                      SQLAlchemy 2.0 async models + repository (DeveloperAccount/ModuleCatalogEntry/SdkPackage)
  clients/                 Resilient HTTP clients to Identity and Access, Multi-tenancy, Auditability, and any catalogued peer's own OpenAPI endpoint
  security/
    jwt_auth.py               Service-to-service JWT (platform-wide shared secret, this module's own inbound protection)
    openapi_security.py       Real OpenAPI security scheme declaration
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI router — developers, catalogue, SDKs, adoption metrics
  schemas/                    Pydantic request/response models
```

## Design notes vs. the LLD

- **A developer's sandbox is a real tenant, not a fenced-off toy.**
  Registration composes two already-built real peers: Identity and
  Access (`POST /identities`, `type="user"`) and Multi-tenancy (`POST
  /tenants`, `tier="sandbox"` — reusing that module's own real `tier`
  field, no second sandbox-tracking system). Sandbox tokens are minted
  on demand by Identity and Access itself; this module never mints or
  stores one.
- **The SDK catalogue is generated from every peer's own real, live
  OpenAPI spec.** `ModuleCatalogService.sync_catalog` calls each
  configured peer's real `GET /openapi.json` — behind that peer's own
  `ServiceAuthMiddleware`, even fetching documentation respects the
  platform's real security model — and `sdk_codegen.py` deterministically
  turns the spec's `paths` into a minimal, real, working Python client.
- **Regeneration is idempotent, keyed off the spec's own content
  hash.** An unchanged spec returns the existing SDK package instead
  of manufacturing churn nobody asked for.
- **Time-to-first-successful-call is computed from real Auditability
  history.** A `total`/`offset` read against Auditability's real
  events endpoint finds the developer sandbox's oldest real event
  directly — no page-size assumption, no full-history scan. Zero
  recorded activity returns `None`, never a fabricated zero.
- **Honest about what isn't measured.** "Support ticket volume" is
  the module table's third key metric; this platform has no
  support-ticketing module, so this LLD does not invent one.

- **Its generated OpenAPI document declares the real auth it enforces**
  (`security/openapi_security.py`) — see Workflow Engine's README and the
  independent architecture assessment's §3.6 for the shared reference
  implementation and full reasoning. `ServiceAuthMiddleware` is plain
  Starlette middleware, invisible to FastAPI's automatic OpenAPI
  generation, so this module's spec previously declared no
  `securitySchemes` at all; `configure_openapi_security` fixes that,
  reusing `jwt_auth.py`'s own `_EXCLUDED_PATHS` as the one source of
  truth for which paths are genuinely unauthenticated.

- **Kubernetes hardening** (`deploy/helm/`; independent architecture
  assessment §3.7) — see Workflow Engine's README for the full reasoning
  and reference implementation. A dedicated ServiceAccount with no
  auto-mounted API token (this module never calls the Kubernetes API);
  pod/container `securityContext` (non-root, read-only root filesystem
  with a small `/tmp` `emptyDir`, all capabilities dropped, a seccomp
  profile); a `NetworkPolicy` restricting ingress to this module's own
  namespace; separate startup/liveness/readiness probe semantics instead
  of two identical probes; and `topologySpreadConstraints` across nodes.

## Running locally

```bash
uv venv && uv pip install -e ".[dev]"
pytest tests/unit                                                    # unit tests, no external services needed

docker compose -f deploy/docker-compose.yml up --build    # full stack incl. Postgres, dependency-stub
```

## Testing tiers

| Tier | What it needs | How to run |
|---|---|---|
| Unit | Nothing — in-memory fakes only | `pytest tests/unit` |
| Integration (isolated) | Real Postgres (`TECTONIC_TEST_POSTGRES_URL` or Docker via `testcontainers`) | `pytest tests/integration` |
