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
  security/                 Service-to-service JWT bearer auth (shared signing key), the entitlement gate, real OpenAPI security scheme declarations
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
- **The evaluation-gated release path (new).** The canary pass-rate gate
  above answers "has this version's traffic looked good over time" —
  a real, blocking check, but a different question from "did this
  version's own most recent evaluation run pass." Evaluation Framework's
  own `POST /gate` engine existed and had a real `GateResultRecord` audit
  trail, but nothing in the platform ever called it. `promote` now also
  resolves the version's latest eval run (via Evaluation Framework's new
  `GET /eval-runs`) and gates it after the pass-rate check succeeds; a
  version whose canary traffic looks fine on aggregate but whose most
  recent run failed a blocking metric threshold is refused with
  `CanaryGateFailedError` (`409`), not promoted around. No eval run yet
  is not a failure — the same convention the pass-rate gate's own
  `insufficient_data` case already establishes for missing evidence. See
  PromptOps' README for the identical pattern applied to prompt-version
  promotion.
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

- **NUL bytes in raw `Query()` string parameters reaching the database
  unvalidated** (ticket #82's platform-wide sweep, following the same bug
  a real CI run found on Multi-tenancy's and Billing and Metering's own
  contract tiers — see either module's own README for the original
  finding). `GET /model-versions`'s `tenant_id`/`model_name` and
  `GET /models/{model_name}/active`'s `target` never ran through a
  NUL-byte validator; fixed with `_reject_null_byte_query()`.

- **The platform's own "unbounded offset" class** (this repo's own
  `CLAUDE.md`-documented recurring bug — already fixed for Billing and
  Metering's, LLM Gateway's, Multi-tenancy's and Workflow Engine's own
  `offset` query params; found again, still open here, when Evaluation
  Framework's own new contract-test tier hit the identical gap and a
  platform-wide grep confirmed it recurred everywhere else that hadn't
  already fixed it). `GET /model-versions`'s `offset` had no upper bound, so a
  value past Postgres's `bigint` range (`> 9223372036854775807`) crashed
  with an unhandled `asyncpg.DataError` instead of a clean `422`. Fixed
  with the identical `le=1_000_000_000` bound those four modules already
  use — comfortably past any real pagination need, comfortably under the
  overflow. Mechanical, not contract-tier-discovered here (this module
  has no contract tier of its own yet) — found by the platform-wide grep
  instead.

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
