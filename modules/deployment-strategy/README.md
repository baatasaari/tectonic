# Deployment Strategy — Module 27

The platform's cloud-agnostic deployment controller: a build artefact is
deployed to a target at some canary traffic percentage, its health is
evaluated against real signals from Evaluation Framework (Module 18)
and FinOps (Module 26), and only promoted to `active` — automatically
superseding whatever was active before — once that composite health
score clears a configurable bar. Full design doc:
[`../../docs/module-27-deployment-strategy.md`](../../docs/module-27-deployment-strategy.md).

## Layout

```
src/deployment_strategy/
  main.py                 FastAPI app, lifespan wiring, /healthz, /metrics
  app_context.py           Process-wide dependency container
  config.py                  Pydantic Settings — LLD config schema
  core/
    domain.py                 DeploymentRecord/CanaryHealthResult dataclasses, the rollout state machine
    ports.py                    Repository, Evaluation Framework client, FinOps client
    fakes.py                     In-memory implementations of every port, for unit tests
    canary_health_calculator.py   Canary Health Calculator — the weighted, real-signal gate
    rollout_service.py              Rollout Service — deploy/promote/rollback, active-deployment query
  db/                      SQLAlchemy 2.0 async models + repository (Deployment)
  clients/                 Resilient HTTP clients to Evaluation Framework and FinOps
  security/                 Service-to-service JWT bearer auth (shared signing key), the entitlement gate, real OpenAPI security scheme declarations
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI router — deploy, canary-health, promote/rollback, active deployment
  schemas/                    Pydantic request/response models
```

## Design notes vs. the LLD

- **Canary health is agent-specific, not just infra metrics.**
  `CanaryHealthCalculator` combines a real groundedness pass rate from
  Evaluation Framework's own `GET /scores` (keyed by this deployment's
  own `deployment_ref` attribution) with a real budget-utilisation
  signal from FinOps's own `GET /cost-reports/{tenant_id}` — a canary
  that's technically healthy but burning far more budget than the
  version it's replacing is not treated as a safe promotion.
- **The same weighted, renormalize-over-available-signals math Agent
  Cards (Module 23) already established, reused here for a promotion
  gate.** Each signal is fetched independently (`_safe_call`-wrapped,
  so a down peer degrades only that component); zero signals with data
  is `insufficient_data`, never a default "healthy" verdict, and
  `promote` treats that exactly like a failure — it never promotes
  optimistically.
- **A real state machine for rollout stages, the same shape Agent
  Marketplace (Module 24) and LLMOps (Module 25) already established.**
  `canary → active` (via `promote`) and `canary`/`active →
  rolled_back` (via `rollback`, a required reason) are the only legal
  transitions (`domain.is_legal_transition`); anything else raises
  `InvalidTransitionError`, a `409`. Promoting a new deployment
  automatically supersedes whatever was previously `active` for the
  same `(tenant_id, service_name, target)` slot.
- **The cost signal is opt-in per deployment, not discovered.** FinOps
  has no "list budget policies for a tenant" endpoint (by that
  module's own design), so a deployment carries an optional
  `budget_policy_id` supplied by the caller at deploy time; when unset,
  the cost signal is simply excluded from the health check rather than
  treated as a failure.
- **Honest about the one signal it doesn't have yet.** A genuinely
  agent-aware canary gate should also watch guardrail-violation rate,
  but Guardrails (Module 14) doesn't yet expose an aggregate,
  queryable violation-rate endpoint — this LLD calls that out
  explicitly as real future work rather than fabricating a signal
  against an endpoint that doesn't exist, the same "documented
  placeholder, not a half-built feature" posture this platform's own
  Agent Marketplace and LLMOps already take.

- **Enforces its own subscription entitlement via `EntitlementGateMiddleware`**
  (`security/entitlement_gate.py`) — see Agent Cards' README and the rollout
  playbook doc (`docs/entitlement-gate-rollout.md`) for the shared reference
  implementation. Layered after `ServiceAuthMiddleware` (authenticate, then
  entitle), it calls Multi-tenancy's real `GET /tenants/{id}/gate?module=deployment-strategy`,
  denying with `402 Payment Required` when the tenant's subscription doesn't
  include this module. It **fails open** if Multi-tenancy is unreachable — a
  deliberate contrast with `ServiceAuthMiddleware`'s zero-trust fail-closed
  posture.

- **Its generated OpenAPI document declares the real auth it enforces**
  (`security/openapi_security.py`) — see Workflow Engine's README and the
  independent architecture assessment's §3.6 for the shared reference
  implementation and full reasoning. `ServiceAuthMiddleware` is plain
  Starlette middleware, invisible to FastAPI's automatic OpenAPI
  generation, so this module's spec previously declared no
  `securitySchemes` at all; `configure_openapi_security` fixes that,
  reusing `jwt_auth.py`'s own `_EXCLUDED_PATHS` as the one source of
  truth for which paths are genuinely unauthenticated.

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
