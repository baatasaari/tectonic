# FinOps — Module 26

The platform's tenant cost-reporting and budget-governance layer: it
combines LLM Gateway (Module 3)'s own live, real spend data with usage
events ingested from any other module into one `CostReport` per
tenant/period, runs a simple run-rate forecast against a configurable
budget policy, and — when that forecast projects a budget breach — lets
a bounded, fully-audited autonomous agent tighten the budget's alert
threshold, one step at a time, never below a configured floor. Full
design doc: [`../../docs/module-26-finops.md`](../../docs/module-26-finops.md).

## Layout

```
src/finops/
  main.py                 FastAPI app, lifespan wiring, /healthz, /metrics
  app_context.py           Process-wide dependency container
  config.py                  Pydantic Settings — LLD config schema
  core/
    domain.py                 UsageEventRecord/BudgetPolicyRecord/OptimisationActionRecord/CostReport, BudgetPeriod
    ports.py                    Repository, LLM Gateway spend client
    fakes.py                     In-memory implementations of every port, for unit tests
    usage_aggregation_service.py  Usage Aggregation Service — combines live LLM Gateway spend + ingested events
    forecasting_service.py        Forecasting Service — run-rate projection, honest insufficient-data floor
    budget_policy_service.py      Budget Policy Service — create/get
    cost_optimisation_agent.py    Cost Optimisation Agent — the one bounded autonomous action
  db/                      SQLAlchemy 2.0 async models + repository (UsageEvent/BudgetPolicy/OptimisationAction)
  clients/                 Resilient HTTP client to LLM Gateway
  security/                 Service-to-service JWT bearer auth (shared signing key), the entitlement gate
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI router — usage events, cost reports, budget policies, evaluate, action audit trail
  schemas/                    Pydantic request/response models
```

## Design notes vs. the LLD

- **Reads LLM Gateway's spend live; never re-derives or duplicates
  it.** `HTTPLLMGatewayClient.tenant_spend` sums the real
  `current_spend` LLM Gateway's own `CostGovernanceEngine` already
  settles after every completion (`GET /admin/virtual-keys` +
  `GET /admin/budgets/{id}`), deduplicated across virtual keys sharing
  one budget policy. LLM Gateway never pushes usage events into this
  module — an explicit design choice to avoid double-counting the same
  dollar twice across two systems.
- **A budget policy here is a FinOps-level, cross-resource concept,
  distinct from LLM Gateway's own per-key spend enforcement.** LLM
  Gateway's `BudgetPolicyRecord` still hard-enforces spend at request
  time for LLM calls specifically; this module's `BudgetPolicyRecord`
  reasons about a tenant's *total* cost (LLM spend plus any other
  ingested usage) and never touches request-time enforcement — it can
  only tighten its own alert threshold, one bounded step at a time,
  never a hard block.
- **The Cost Optimisation Agent has exactly one possible action.**
  `CostOptimisationAgent.evaluate` may lower a budget policy's
  `alert_threshold_pct` by `alert_threshold_step`, clamped at
  `min_alert_threshold_pct` — and only when the run-rate forecast
  actually projects a breach of the budget's `limit_amount`. It never
  blocks spend, never edits `limit_amount`, and every action taken is
  persisted with `previous_value`/`new_value`/`reason` for audit
  (`GET /budget-policies/{id}/actions`).
- **Forecasts are honest about insufficient data.**
  `ForecastingService.forecast` returns `None` — not a wild
  extrapolation — when less than 5% of the budget period has elapsed,
  the same insufficient-data-over-fabrication posture Agent Cards
  (Module 23) and LLMOps (Module 25) already established for their own
  real-signal computations.
- **Wire-compatible `BudgetPeriod` with LLM Gateway.** This module's
  `BudgetPeriod` uses the exact same two values (`daily`, `monthly`) as
  LLM Gateway's own, not a guessed vocabulary of its own.
- **Connection pooling sized against this module's own Helm chart**
  (`deploy/helm/finops/values.yaml`'s `autoscaling.maxReplicas`), the
  platform's standard formula, and `GET /budget-policies/{id}/actions`
  is paginated (`limit`/`offset`, default 50/max 200) from its first
  version.

- **Enforces its own subscription entitlement via `EntitlementGateMiddleware`**
  (`security/entitlement_gate.py`) — see Agent Cards' README and the rollout
  playbook doc (`docs/entitlement-gate-rollout.md`) for the shared reference
  implementation. Layered after `ServiceAuthMiddleware` (authenticate, then
  entitle), it calls Multi-tenancy's real `GET /tenants/{id}/gate?module=finops`,
  denying with `402 Payment Required` when the tenant's subscription doesn't
  include this module. It **fails open** if Multi-tenancy is unreachable — a
  deliberate contrast with `ServiceAuthMiddleware`'s zero-trust fail-closed
  posture.

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
