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

- **A real HTTP trigger for `MeteringService.meter_tenant()`** (ticket
  #82) — the service itself was already real and tested, but nothing in
  this module's own real API could ever call it; a real deployment's
  scheduler is expected to call this periodically. Added
  `POST /v1/billing/tenants/{tenant_id}/meter?period=...`.

- **`PricingPlanService.create()`'s own entitlement-sync is a real
  *replace*, not an add** (ticket #82's own Phase 2 support-agent slice
  surfaced this seeding a tenant for the first time with a plan that
  didn't name every module it needed): creating a tenant-specific plan
  syncs Multi-tenancy's entitlements to exactly the module names in that
  plan's own `unit_prices` (by design — see this service's own
  docstring), which silently clobbers a wider entitlement grant made
  moments earlier if the plan doesn't also name every one of those
  modules. Not a bug in this module (the sync is deliberate and
  documented) — the seed script calling it needed fixing instead; noted
  here since it's exactly the kind of cross-module interaction a
  single-module test would never catch.

- **NUL bytes in raw `Query()` string parameters reaching Postgres
  unvalidated** (ticket #82's own CI wiring for `tests/product-slices/`
  — a real GitHub Actions run of this module's own contract tier, not
  reproducible locally against this sandbox's own Hypothesis random
  seed, first surfaced it). A raw `Query()` parameter on `GET
  /pricing-plans`, `GET /invoices`, and `GET /usage-records`
  (`tenant_id`, `period`) never runs through a body field's own
  NUL-byte validator — it reached Postgres raw and 500'd
  (`UntranslatableCharacterError`) instead of a clean `422`. Fixed with
  a small `_reject_null_byte_query()` applied at the top of each of
  those three routes; `tests/unit/test_routes_billing_and_metering.py`
  pins the regression directly rather than relying on fuzzing luck to
  rediscover it. Same bug class Multi-tenancy's own README documents
  the identical fix for; a platform-wide sweep (this repeats in several
  other modules' own list endpoints too, per a grep across the repo) is
  real, separately-scoped follow-up work, not done here.

- **`anyio` 4.15.0 (released the day this was found) broke every
  contract-tier module's dev install.** It dropped/broke the
  `start_blocking_portal` lazy-import alias `starlette-testclient` 0.4.1
  depends on, so a fresh `uv pip install -e ".[dev]"` (this module's own
  pre-existing local `.venv`, created before that release, was
  unaffected) started resolving the broken version and every contract
  test failed at import (`AttributeError: module 'anyio' has no
  attribute 'start_blocking_portal'`) rather than at any real assertion.
  Confirmed as upstream dependency drift unrelated to this repo's own
  history: identical failure on all seven contract-tier modules, on the
  base branch's own CI run, and PyPI's own release date for 4.15.0.
  Pinned `anyio<4.15` in `pyproject.toml`'s dev deps, resolving back to
  the known-good `4.14.2`. (LLM Gateway's and Multi-tenancy's own
  READMEs document the same pin alongside a real bug it let their own
  contract tiers actually run against for the first time.)

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
| Contract | Real Postgres (same as Integration) | `pytest tests/contract` |

The contract tier (`tests/contract/`) is this platform's reference
implementation of Phase 1's CI supply-chain gates: `schemathesis`/
Hypothesis drive schema-conformant-but-otherwise-arbitrary requests at
this module's real, running app (real middleware, real Postgres) for
every operation its own generated OpenAPI document declares, and any
`5xx` is a genuine contract violation — this module's own documented
`422` isn't actually enforced. It found four real bugs on its first
runs (unbounded `offset`, a NUL byte in a request string, a non-UUID
path segment, an invalid `status` filter — all now fixed; see the
module docstring in `tests/contract/test_openapi_contract.py` for the
full account of each). CI (`.github/workflows/ci.yml`) runs this tier
automatically for any module with a `tests/contract/` directory.

CI also generates a CycloneDX SBOM of this module's real runtime
dependency set and signs it keylessly with Sigstore via the workflow
run's own GitHub Actions OIDC identity (the `sbom-and-sign` job,
platform-wide, all 34 modules) — no long-lived signing key for the
repo to hold. Verify a downloaded SBOM's provenance with:

```bash
sigstore verify github --cert-identity <workflow identity> \
  --repository <owner>/tectonic sbom.cyclonedx.json
```
