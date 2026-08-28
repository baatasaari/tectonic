# PromptOps — Module 29

The platform's prompt registry, A/B-testing gate and bounded
reflection-based optimiser: a prompt template is registered as a
`draft` version, pitted against another version in a real,
statistically-gated A/B test read from Evaluation Framework's own
production scores, and only promoted to `active` — automatically
superseding whatever was active before — once that test actually
clears significance. A bounded optimiser agent can propose new draft
versions from a struggling version's real failure pattern, but never
promotes anything itself. Full design doc:
[`../../docs/module-29-promptops.md`](../../docs/module-29-promptops.md).

## Layout

```
src/promptops/
  main.py                 FastAPI app, lifespan wiring, /healthz, /metrics
  app_context.py           Process-wide dependency container
  config.py                  Pydantic Settings — LLD config schema
  core/
    domain.py                 PromptVersionRecord/ABTestRecord dataclasses, the version state machine
    statistics.py               Two-proportion z-test (stdlib math.erf, no new dependency)
    ports.py                     Repository, Evaluation Framework client, LLM Gateway client
    fakes.py                      In-memory implementations of every port, for unit tests
    prompt_registry_service.py     Prompt Registry — register/list/get
    ab_testing_service.py           A/B Testing Service — the real-evidence significance gate
    drift_detection_service.py       Drift Detection Service — reuses the same z-test post-launch
    reflection_optimiser.py           Reflection Optimiser — the one bounded autonomous action
  db/                      SQLAlchemy 2.0 async models + repository (PromptVersion/ABTest)
  clients/                 Resilient HTTP clients to Evaluation Framework and LLM Gateway
  security/                 Service-to-service JWT bearer auth (shared signing key), the entitlement gate, real OpenAPI security scheme declarations
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI router — register, A/B test, drift-check, reflect, active version
  schemas/                    Pydantic request/response models
```

## Design notes vs. the LLD

- **A/B testing decided by a real statistical test.**
  `ABTestingService.evaluate` runs an honest two-proportion z-test over
  both versions' real pass/fail history from Evaluation Framework;
  `conclude` refuses to pick a winner (`409`) until the p-value clears
  the configured significance level, and returns `insufficient_data`
  below `min_sample_size_per_arm` per arm rather than a coin-flip
  verdict.
- **The same statistic reused for drift detection after launch.**
  `DriftDetectionService` compares an active version's pass rate right
  now against its pass rate at the moment it was promoted — a real,
  computed drift incident, not a vague warning.
- **The Reflection Optimiser proposes, never auto-deploys.**
  `ReflectionOptimiser.propose` reads a version's real failing-metric
  summary from Evaluation Framework, asks LLM Gateway to draft an
  improved template, and returns it as a brand-new `draft` version —
  never overwrites the original, never starts an A/B test, never
  promotes anything. It also declines to act (`None`/`204`) when the
  version is already performing well or there isn't enough evidence
  yet — the same "one bounded action, everything else stays manual"
  shape FinOps' own Cost Optimisation Agent already established.
- **A real state machine for prompt versions**, the same shape Agent
  Marketplace, LLMOps and Deployment Strategy already established:
  `draft → testing` (via `start`) → `active`/`archived` (via
  `conclude`); `active → archived` on the next promotion. Anything
  outside that legal set is a `409` (`InvalidTransitionError`).

- **Enforces its own subscription entitlement via `EntitlementGateMiddleware`**
  (`security/entitlement_gate.py`) — see Agent Cards' README and the rollout
  playbook doc (`docs/entitlement-gate-rollout.md`) for the shared reference
  implementation. Layered after `ServiceAuthMiddleware` (authenticate, then
  entitle), it calls Multi-tenancy's real `GET /tenants/{id}/gate?module=promptops`,
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
