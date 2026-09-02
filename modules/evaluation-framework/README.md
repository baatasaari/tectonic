# Evaluation Framework — Module 18

Scores agent outputs against faithfulness, coherence, tool-trace
correctness and domain-specific metrics, both as a CI/CD gate before
deployment and as continuous sampling against live production traffic.
Full design doc:
[`../../docs/module-18-evaluation-framework.md`](../../docs/module-18-evaluation-framework.md).

## Layout

```
src/evaluation_framework/
  main.py                 FastAPI app, lifespan wiring, /healthz, /metrics
  app_context.py           Process-wide dependency container
  config.py                 Pydantic Settings — LLD config schema
  core/
    domain.py                EvalRun/MetricScore/GateResult/DomainMetricPack dataclasses
    ports.py                   Repository, LLM Gateway
    fakes.py                     In-memory implementations of every port, for unit tests
    similarity.py                  Term-frequency cosine similarity — the heuristic-fallback's basis
    metric_adapters.py               Heuristic metrics (coherence, tool-trace, domain packs) + LLM-judge fallback
    deepeval_adapter.py                Real `deepeval.metrics.FaithfulnessMetric` integration
    evaluator.py                       Orchestrates a metric set against one agent output
    gate_engine.py                      Aggregates MetricScores into a pass/fail GateResult
    sampler.py                           Production Sampler — deterministic hash-based sampling
  cli/main.py               `agenteval run --gate` — CI/CD pipeline entrypoint
  db/                      SQLAlchemy 2.0 async models + repository
  clients/                 HTTP client for LLM Gateway (LLM-as-judge fallback)
  security/                 Service-to-service JWT bearer auth (shared signing key), the entitlement gate, real OpenAPI security scheme declarations
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI router — evaluate, gate, domain-packs, scores, sample
  schemas/                    Pydantic request/response models
```

## Design notes vs. the LLD

- **Resiliency.** Every outbound HTTP call this module makes to a peer module goes through `ResilientHTTPClient` (`clients/resilience.py`): exponential-backoff retry on network errors and 5xx responses (never 4xx — a client error means the peer already processed the request and rejected it, so retrying just repeats the mistake), and a circuit breaker (`aiobreaker`) that opens after repeated failures so a struggling peer gets a break instead of a retry storm, and this module fails fast instead of piling up requests against a peer that's already down.

- **Eval library adapters — `faithfulness` is real DeepEval, corrected
  after review.** The LLD calls for wrapping DeepEval, Ragas and an
  OpenAI-Evals-compatible format behind one interface. The first version
  of this module assumed DeepEval "pulls in heavy dependency trees
  (torch, transformer model downloads) unsuited to this module's offline
  unit-test tier" and reimplemented faithfulness as a term-overlap
  heuristic instead of using it — that assumption was never actually
  verified and turned out to be wrong: `deepeval` installs in a few
  seconds with ~35 lightweight dependencies (no torch, no local models;
  its LLM-as-judge calls go through a small `DeepEvalBaseLLM` interface
  you implement). `core/deepeval_adapter.py` now genuinely wraps the real
  `deepeval.metrics.FaithfulnessMetric`, via `DeepEvalLLMGatewayModel`
  routing every one of DeepEval's internal judge calls through this
  module's own LLM Gateway client — consistent with the platform rule
  that LLM Gateway is the only module allowed to call a model provider
  directly. `core/metric_adapters.py`'s original term-overlap
  implementation (`HeuristicFaithfulnessMetric`) is kept as the automatic
  fallback when the real DeepEval call fails (LLM Gateway unreachable,
  unparseable model output) — the same real-call-for-the-common-case,
  documented-fallback-for-the-degraded-case pattern used elsewhere in
  this platform. `coherence` and `tool_trace_correctness` remain local
  heuristics — DeepEval has no equivalent off-the-shelf metric worth
  wrapping for either. Ragas remains unintegrated; the technique proven
  here for DeepEval would apply equally to it. Any metric name covered by
  neither DeepEval nor this local registry falls back to an LLM Gateway
  LLM-as-judge call, preserving the LLD's "multiple metric sources
  feeding one interface" shape.
- **Testing DeepEval offline.** `deepeval`'s metric classes make several
  internal LLM calls per evaluation (extract truths, extract claims,
  judge each claim, summarise a reason) using its own prompt templates —
  real prompts, not a mock of DeepEval itself. The unit tests
  (`test_deepeval_adapter.py`) and the dependency-stub
  (`stubs/dependency-stub/app.py`'s `/v1/complete`) both script responses
  to those exact templates, computing per-claim verdicts from real
  token-overlap recall against the retrieval context rather than a fixed
  canned answer — an unfaithful claim genuinely scores lower than a
  faithful one in these tests, the same as it would against a real
  backing model.
- **Domain-specific metrics.** The LLD says these are "ported directly
  from AgentEval's existing custom metrics" — that codebase isn't
  available in this build environment, so `financial_guidance_compliance`
  is a fresh, simple reimplementation of the same intent (checks for a
  disclaimer, flags guaranteed-return language), not a port.
- **Production sampler.** The LLD specifies a Kafka consumer sampling
  live traffic. This module has no Kafka broker to consume from in this
  build (the same Kafka-to-HTTP substitution used elsewhere in this
  platform, e.g. Sentinel Agents' event ingestion) — `POST
  /v1/evaluation-framework/sample` is the HTTP substitute. The actual
  sampling decision (`core/sampler.py`) is still a real, testable
  component: a deterministic hash of `interaction_id` against the
  configured `sample_rate`, not `random()`, so a given interaction always
  samples the same way.
- **Pagination on `GET /scores`.** Added `limit`/`offset` query params
  (default 50, max 200) and a `MetricScoreListResponse` envelope
  (`items`/`total`/`limit`/`offset`) — this endpoint previously returned
  every matching score row unbounded, a real scaling gap for a tenant
  with a large evaluation history. Ordered by `created_at` descending
  (newest score first) for stable pagination.
- **CLI.** `agenteval run --gate` reimplements the LLD's described
  AgentEval CLI pattern against this module's own HTTP API (`click` +
  `httpx`, both real, lightweight dependencies) rather than porting
  AgentEval's actual CLI code, which isn't available here.
- **Feedback loop to LLM Gateway / Context Engineering / PromptOps.**
  The LLD's sequence diagram has those modules query this module's
  Postgres directly for recent quality scores. Every module in this
  platform owns its own database (ports-and-adapters, no cross-module DB
  access), so that feedback loop is `GET /v1/evaluation-framework/scores`
  being polled by those modules instead — the same data, reached through
  this module's API rather than its storage.
- **Postgres integration tests** — the repository layer is now also tested
  against a real Postgres (`tests/integration/`, opt-in via
  `TECTONIC_TEST_POSTGRES_URL` or Docker+testcontainers), covering
  `EvalRun.metrics_evaluated` list-order-preserving JSONB round trips, a real
  UUID primary key round trip through `get_eval_run`, float-type fidelity on
  `DomainMetricPack.custom_thresholds`, and a multi-row filtered query
  (`list_metric_scores_for_tenant`) hitting only rows matching both tenant and
  agent_ref — none of which SQLite's unit-tier fakes can reliably prove. See
  `tests/integration/conftest.py` for how the Postgres instance is obtained.
  This tier's presence prompted a platform-wide sweep of every module's
  `db/models.py` for the same class of bug: `Mapped[datetime]` columns missing
  `DateTime(timezone=True)` despite the Alembic migration already defining
  them as timestamptz and the domain layer's defaults being tz-aware —
  invisible under SQLite, but a real correctness bug against Postgres once a
  domain default (or an explicit value) is written. Found and fixed here too.

- **Connection pooling tuned to replica count.** SQLAlchemy's out-of-
  the-box defaults (`pool_size=5`, `max_overflow=10`) are the same
  regardless of how many pods are running — at this module's own
  `deploy/helm/evaluation-framework/values.yaml` `autoscaling.maxReplicas: 20`,
  that's up to 300 connections to this module's own Postgres
  instance from this module alone at full autoscale, with no one having
  deliberately decided that number. `db/session.py`'s `make_engine` now
  passes explicit, configurable `pool_size=5` /
  `max_overflow=2` (`db_pool_size`/`db_max_overflow`
  Settings, env-overridable) sized so this module's own steady-state
  total stays at ~100 connections and its full-burst total at ~150,
  even at `maxReplicas`. `pool_recycle=1800s` also avoids stale
  connections behind a cloud LB/proxy's own idle-connection timeout —
  a real, independent gap, not just a replica-count one.

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
  `HTTPLLMGatewayClient` makes — a token minted to call one peer is
  rejected if replayed against a different one. The shared secret
  (`TECTONIC_JWT_SHARED_SECRET`, one Kubernetes Secret referenced by
  every module's Helm chart under this same literal env var name, not a
  per-module-prefixed one) defaults to an obviously-insecure placeholder
  for zero-config local dev/tests; `main.py` logs a startup warning if
  it's still active. This is service-to-service auth for inter-module
  calls, not the platform's external-facing user-auth story — a real API
  gateway/OAuth layer in front of the platform's own entry points is a
  separate, larger concern, out of scope here.

- **Enforces its own subscription entitlement via `EntitlementGateMiddleware`**
  (`security/entitlement_gate.py`) — see Agent Cards' README and the rollout
  playbook doc (`docs/entitlement-gate-rollout.md`) for the shared reference
  implementation. Layered after `ServiceAuthMiddleware` (authenticate, then
  entitle), it calls Multi-tenancy's real `GET /tenants/{id}/gate?module=evaluation-framework`,
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

- **NUL bytes in raw string query parameters reaching the database
  unvalidated** (ticket #82's platform-wide sweep, following the same bug
  a real CI run found on Multi-tenancy's and Billing and Metering's own
  contract tiers — see either module's own README for the original
  finding; this module wasn't in that sweep's original module list —
  found by re-grepping the whole platform for the same pattern once the
  sweep was otherwise done). `GET /scores`'s `tenant_id`/`agent_ref`
  never ran through a NUL-byte validator — unlike its siblings, these
  were plain, un-wrapped `str` function parameters rather than an
  explicit `Query()` default, which is why the earlier grep for
  `Query(` missed this file; fixed with `_reject_null_byte_query()`. No
  route-level test file existed for this module before this fix —
  `tests/unit/test_routes_evalfw.py` (new) pins just this regression;
  comprehensive route coverage remains a real, separately-scoped gap.

- **`GET /eval-runs` (new).** Neither `POST /gate` nor `GET /scores`
  gave a caller a way to find the `eval_run_id` a specific agent_ref's
  most recent evaluation actually ran under — `/scores` returns
  individual `MetricScoreRecord` rows, not grouped by run, and `/gate`
  requires an `eval_run_id` the caller has to already know. This closed
  that gap: `tenant_id`/`agent_ref`-scoped, most-recent-first (by
  `started_at`), paginated the same way as `/scores`. Built specifically
  so PromptOps' `ABTestingService.conclude` and LLMOps'
  `RolloutService.promote` could resolve "the latest eval run for this
  version" before calling `/gate` on it — see those modules' own READMEs
  for the evaluation-gated release path this unblocks. New composite
  index (`ix_eval_runs_tenant_agent` on `eval_runs(tenant_id,
  agent_ref)`, migration `0002`) backs the query; scores aren't included
  in list responses (an N+1 a caller resolving a bare id doesn't need).

- **Contract-test tier (new; ticket #73/#80's rollout continued).**
  `tests/contract/` — real OpenAPI-schema-driven fuzzing (schemathesis +
  Hypothesis) against a live app instance and real Postgres, ported from
  Identity and Access's own reference `conftest.py`. Picked as the next
  module for this rollout specifically because this session's own
  evaluation-gated-release-path work just added a never-fuzzed route
  (`GET /eval-runs`) and made this module's `/gate` verdict load-bearing
  for both PromptOps' and LLMOps' own release gates. Its first several
  runs found four real, previously-invisible bugs:
  - **NUL bytes in Pydantic *body* fields**, not just the raw `Query()`
    string parameters ticket #82's sweep already covered — `POST
    /evaluate`'s `tenant_id`/`agent_ref`/`trigger_source`/`metric_set`
    items, `POST /gate`'s `tenant_id`/`eval_run_id`/`environment`, `POST
    /domain-packs`'s `tenant_id`/`pack_name`, `POST /sample`'s
    `tenant_id`/`agent_ref`/`metric_set` items all reached
    `session.execute()` raw instead of a clean `422` — fixed with the
    established `_reject_null_byte` `field_validator` pattern (LLM
    Gateway's `schemas/admin.py`).
  - **A NUL byte survives inside a `dict` *key* too** — `POST
    /domain-packs`'s `custom_thresholds` round-trips as a real `jsonb`
    column, and jsonb's own text-based storage rejects an embedded NUL
    exactly like `text`/`varchar` does, even nested inside an object key.
    Fixed with the same per-key validator Billing and Metering's own
    `unit_prices` already established.
  - **A syntactically-invalid UUID handed straight to `session.get()`**
    — `POST /gate`'s `eval_run_id` crashed with an unhandled
    `asyncpg.DataError` instead of a clean `404` (`GateEngine.gate`
    already had a documented not-found path; nothing reached it). Fixed
    with `db/repository.py`'s own `_is_valid_uuid` guard, the same
    pattern Identity and Access's `get_identity`/`get_group`/etc.
    already established.
  - **The platform's own "unbounded offset" class** (this repo's
    `CLAUDE.md`-documented recurring bug: already fixed for Billing and
    Metering's, LLM Gateway's, Multi-tenancy's and Workflow Engine's own
    `offset` query params) — `GET /eval-runs`'s and `GET /scores`'s
    `offset` had no upper bound, so a value past Postgres `bigint` range
    crashed instead of a clean `422`. Fixed with the same `le=
    1_000_000_000` bound those modules use. **Left deliberately
    unfixed/out of scope of this pass**: this same gap is still open on
    every *other* module's `offset` query params that don't yet have an
    `le=` bound (most of the platform, Identity and Access included,
    despite already having its own contract tier — schemathesis's
    integer strategy doesn't reliably generate an overflow value every
    run, so this can pass by chance) — a real, sourced next candidate
    for this same mechanical-leverage backlog item, not silently swept
    here since it's a platform-wide change well beyond this module.
  All four were unreachable from `pytest tests/unit` (SQLite's fake
  can't reproduce a real Postgres encoding/type error) — `tests/
  integration/test_repository_postgres.py`'s new
  `test_a_non_uuid_eval_run_id_returns_none_instead_of_crashing` is the
  one that needed real Postgres; the other three got route-level unit
  regressions since `InMemoryEvaluationFrameworkRepository` never
  reaches the database at all. Hypothesis's randomized example
  generation means a single green contract-tier run doesn't fully prove
  the absence of further bugs of this shape — this pass reran it
  repeatedly (4 consecutive clean runs after all four fixes) rather than
  trusting one pass, the same discipline this repo's own `CLAUDE.md`
  documents for this tier.

## Running locally

```bash
uv venv && uv pip install -e ".[dev]"
pytest                                                    # unit tests, no external services needed

docker compose -f deploy/docker-compose.yml up --build    # full stack incl. Postgres, dependency-stub
```
