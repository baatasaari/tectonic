# LLMOps — Module 25

The platform's model registry and staged-rollout controller: a new
model version is registered, deployed to a target at some canary
traffic percentage, evaluated against real production scores from
Evaluation Framework (Module 18), and only promoted to `active` — once
that evidence clears a configurable bar. Full design doc:
[`../../docs/module-25-llmops.md`](../../docs/module-25-llmops.md).

## Layout

```
src/llmops/
  main.py                 FastAPI app, lifespan wiring, /healthz, /metrics
  app_context.py           Process-wide dependency container
  config.py                  Pydantic Settings — LLD config schema
  core/
    domain.py                 ModelVersionRecord/DeploymentRecord dataclasses, the rollout state machine
    ports.py                    Repository, Evaluation Framework client
    fakes.py                     In-memory implementations of every port, for unit tests
    model_registry_service.py     Model Registry Service — register/list versions
    canary_evaluation_service.py   Canary Evaluation Service — the real-evidence gate
    rollout_service.py              Rollout Service — start_canary/promote/rollback, active-version query
  db/                      SQLAlchemy 2.0 async models + repository (ModelVersion/Deployment)
  clients/                 Resilient HTTP client to Evaluation Framework
  security/                 Service-to-service JWT bearer auth (shared signing key), the entitlement gate
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI router — register, start-canary, canary-gate, promote/rollback, active version
  schemas/                    Pydantic request/response models
```

## Design notes vs. the LLD

- **The canary gate never passes on a timer or on volume alone.**
  `CanaryEvaluationService.evaluate` requires at least
  `min_canary_sample_size` real evaluation samples (from Evaluation
  Framework's own `GET /scores`) before it renders any verdict at all —
  fewer than that is `insufficient_data`, not a pass — and then checks
  the real pass rate against `min_canary_pass_rate`. `promote` always
  re-runs this check; it never trusts an earlier pass, so there's no
  window where a regression introduced after the last check slips
  through on a stale verdict.
- **Evaluation attribution via a dedicated `agent_ref` convention.**
  `canary_evaluation_service.evaluation_ref` builds
  `model:{model_name}:{version}` as the `agent_ref` a model version's
  own evaluation runs must be tagged with — distinct from
  `artifact_ref` (a provider-specific identifier an operator shouldn't
  need to know to find the version's own scores).
- **A real state machine for rollout stages, the same shape Agent
  Marketplace (Module 24) already established.** `canary → active` (via
  `promote`) and `canary`/`active → rolled_back` (via `rollback`, a
  required reason) are the only legal transitions
  (`domain.is_legal_transition`); anything else raises
  `InvalidTransitionError`, a `409`. Promoting a new deployment
  automatically supersedes whatever was previously `active` for the
  same `(tenant_id, model_name, target)` — never two simultaneously
  "active" deployments for the same slot.
- **Explicitly does not reconfigure LLM Gateway (Module 3)'s live
  routing.** This module is the source of truth for which version
  *should* be active; a consuming module reading that decision (via
  `GET /models/{model_name}/active`) and actually acting on it — e.g.
  LLM Gateway polling or being pushed this module's decision — is real,
  valuable future work this LLD calls out explicitly rather than
  quietly half-wiring it here, the same "documented placeholder, not a
  half-built feature" posture Agent Marketplace's own
  `external_listing_enabled` already takes.
- **Connection pooling and pagination, built in from day one.** Sized
  against this module's own Helm chart's `autoscaling.maxReplicas` from
  the start (this platform's standard formula), and `GET
  /model-versions` is paginated (`limit`/`offset`, default 50/max 200)
  from its first version.

- **Enforces its own subscription entitlement via `EntitlementGateMiddleware`**
  (`security/entitlement_gate.py`) — see Agent Cards' README and the rollout
  playbook doc (`docs/entitlement-gate-rollout.md`) for the shared reference
  implementation. Layered after `ServiceAuthMiddleware` (authenticate, then
  entitle), it calls Multi-tenancy's real `GET /tenants/{id}/gate?module=llmops`,
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
