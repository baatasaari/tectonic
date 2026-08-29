# Billing and Metering — Module 33

Turns real per-tenant usage signals from other platform modules into
metered usage records and invoices. `"llm.cost_usd"` is read straight
from FinOps (Module 26)'s own real `GET /v1/finops/cost-reports/{tenant_id}`;
every other metered resource in a pricing plan is treated as a real
`source_module` name and counted from Auditability (Module 20)'s own
real `GET /v1/auditability/events` — no second usage-tracking pipeline
of its own. A tenant-specific plan's module list is also pushed to
Multi-tenancy (Module 30)'s feature-flag store, so what a tenant is
billed for is what its subscription actually entitles it to elsewhere
in the platform. Full design doc: [`../../docs/module-33-billing-and-metering.md`](../../docs/module-33-billing-and-metering.md).

## Layout

```
src/billing_and_metering/
  main.py                 FastAPI app, lifespan wiring, /healthz, /metrics
  app_context.py           Process-wide dependency container
  config.py                  Pydantic Settings — LLD config schema
  core/
    domain.py                 PricingPlanRecord/MeteredUsageRecord/InvoiceRecord, the invoice lifecycle state machine
    period.py                   The [start, end) window a period name resolves to — mirrors FinOps's own definition
    ports.py                    Repository, the two real platform-peer client ports
    fakes.py                     In-memory implementations of every port, for unit tests
    pricing_plan_service.py       Pricing Plan Service — create/get/list, resolve a tenant's active plan, sync entitlements
    metering_service.py             Metering Service — pulls real usage from FinOps + Auditability
    invoice_service.py                Invoice Service — aggregates usage into lines/total, draft→finalized
  db/                      SQLAlchemy 2.0 async models + repository (PricingPlan/UsageRecord/Invoice/InvoiceLine)
  clients/                 Resilient HTTP clients to FinOps + Auditability + Multi-tenancy
  security/
    jwt_auth.py               Service-to-service JWT (platform-wide shared secret, this module's own inbound protection)
    openapi_security.py       Real OpenAPI security scheme declaration
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI router — pricing plans, invoices, usage records
  schemas/                    Pydantic request/response models
```

## Design notes vs. the LLD

- **Usage is metered from real platform signals, not invented here.**
  `MeteringService` calls FinOps's real cost-report endpoint for LLM
  spend and Auditability's real event-list endpoint (using the `total`
  it already returns) for everything else — two already-built,
  independently audited modules are the metering source of truth.
- **What gets metered is driven by the pricing plan.** A plan's
  `unit_prices` keys ARE the metered resources; pricing a new module
  in is a plan edit, never a code change.
- **Metering accuracy is a real flag on every invoice, not an
  assumption.** A metering-source failure skips that resource's usage
  record and flips the invoice's `complete` flag to `False` — unknown
  usage is never silently recorded as zero usage.
- **Invoices are a real one-way state machine.** `draft → finalized`
  only — the same one-way `_LEGAL_TRANSITIONS` shape Secrets and
  Credential Management (Module 32) established for its own
  revocation lifecycle.
- **Pricing is entitlement, not just a billing record — in both
  directions.** Creating a tenant-specific plan (`tenant_id` set, not
  the global default) wholesale-syncs its `unit_prices` keys — minus
  `"llm.cost_usd"`, which is a metered resource, not a module — to
  Multi-tenancy's `POST /tenants/{id}/entitlements`, so every other
  module's `gate(tenant_id, module=...)` check reflects the plan the
  instant it's created. And the other direction now holds too:
  `MeteringService` calls that same real
  `GET /tenants/{id}/gate?module=...` before metering each resource,
  so a tenant downgraded away from a module (entitlements revoked,
  edited elsewhere, or just out of sync with the plan) stops being
  billed for it on the very next metering run, not just blocked from
  calling it. `"llm.cost_usd"` is gated against the real `llm-gateway`
  module name, since it isn't itself a module. A denied entitlement
  skips that resource without marking the invoice `complete: false` --
  it's a deliberate, known exclusion, not missing data. Both directions
  fail OPEN when Multi-tenancy is unreachable (meter/bill as if
  entitled, sync silently degraded) -- the same posture
  `EntitlementGateMiddleware` takes platform-wide: a commercial gate
  must never turn an outage into missed revenue on top of itself.
- **The metering ledger is now genuinely idempotent, tied to a real
  unique key.** Previously, re-running metering for a period already
  metered (a retried scheduler job, a re-triggered
  `POST /invoices/generate`) created a second, duplicate
  `MeteredUsageRecord` per resource -- summed together on the next
  invoice, silently double-billing the tenant. Every usage number now
  goes through `BillingRepository.upsert_usage_record`, a real
  Postgres `INSERT ... ON CONFLICT (tenant_id, period, resource) DO
  UPDATE ... RETURNING` (the same atomic-upsert shape Multi-tenancy's
  own `increment_quota_counter` already uses for a different table) --
  re-metering a period converges to one authoritative row per resource
  instead of accumulating duplicates. `InvoiceService.generate_invoice`
  is idempotent the same way: a real `UNIQUE (tenant_id, period)`
  constraint on `invoices` backs a check-then-update-or-create flow (a
  concurrent race falls back to the winner's own row via a caught
  `IntegrityError`, verified under 5 real concurrent callers in
  `tests/integration`), a `draft` invoice for an already-metered period
  gets its lines wholesale-replaced rather than duplicated, and a
  `finalized` one is returned completely unchanged -- never re-metered,
  let alone re-totaled, no matter what usage arrives afterward.

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
