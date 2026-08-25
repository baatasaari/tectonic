# Multi-tenancy — Module 30

The platform's tenant registry and isolation-verification layer: every
tenant's lifecycle (`active`/`suspended`/`deleted`) is governed here,
and a real, executable probe periodically confirms that a tenant-scoped
query against any registered platform module actually returns only
that tenant's own records. Full design doc:
[`../../docs/module-30-multi-tenancy.md`](../../docs/module-30-multi-tenancy.md).

## Layout

```
src/multi_tenancy/
  main.py                 FastAPI app, lifespan wiring, /healthz, /metrics
  app_context.py           Process-wide dependency container
  config.py                  Pydantic Settings — LLD config schema, incl. probe_targets
  core/
    domain.py                 TenantRecord/IsolationProbeResult dataclasses, the tenant lifecycle state machine
    ports.py                    Repository, the one generic tenant-scoped list client shape
    fakes.py                     In-memory implementations of every port, for unit tests
    tenant_registry_service.py    Tenant Registry — register/suspend/reactivate/delete, the gate check
    isolation_probe_service.py     Isolation Probe Service — the real, executable isolation check
  db/                      SQLAlchemy 2.0 async models + repository (Tenant/IsolationProbeResult)
  clients/                 Resilient HTTP client reused against every registered probe target
  security/                 Service-to-service JWT bearer auth (shared signing key)
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI router — tenant lifecycle, gate, isolation probes
  schemas/                    Pydantic request/response models
```

## Design notes vs. the LLD

- **Isolation is actively verified, not just assumed.** Every module in
  this platform already follows one identical list-endpoint contract —
  `GET .../resource?tenant_id=X` → `{"items": [...each with its own
  tenant_id...]}`. `IsolationProbeService` exploits that directly: it
  calls a target module's real list endpoint scoped to one tenant and
  checks that every returned item's own `tenant_id` actually matches —
  a genuine, executable check, no per-module adapter code needed.
- **The LLD's own key metric is a real, wired counter.**
  `multi_tenancy_isolation_breach_incidents_total` increments by the
  actual number of foreign records a probe run found.
- **Fails closed.** A probe against an unreachable target is recorded
  `passed=False` with a `probe_unavailable` reason — never a silent
  assumed-fine.
- **A real state machine for tenant lifecycle**, the same shape Agent
  Marketplace, LLMOps, Deployment Strategy and PromptOps already
  established: `active ↔ suspended`, either → `delete` (terminal).
  `GET /tenants/{id}/gate` is the one real integration point every
  other module's request path should call before serving a request.

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
