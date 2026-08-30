# Guardrails — Module 14

The dual-stage policy enforcement point for every input reaching an LLM
and every output leaving one. Every module that calls LLM Gateway routes
the request and response through this module first (input check before
the call, output check after). Full design doc:
[`../../docs/module-14-guardrails.md`](../../docs/module-14-guardrails.md).

## Layout

```
src/guardrails/
  main.py                 FastAPI app, lifespan wiring, /healthz, /metrics
  app_context.py           Process-wide dependency container
  config.py                 Pydantic Settings — LLD config schema
  core/
    domain.py                PolicyProfile/InterventionLog/RedTeamRun/BypassIncident dataclasses
    ports.py                   Repository, LLM Gateway, Sentinel Agents
    fakes.py                    In-memory implementations of every port, for unit tests
    pii_detector.py               Presidio PII Detector — regex/heuristic detection + redaction
    jailbreak_detector.py           Jailbreak/Injection Detector — strong patterns + ambiguous fallback
    similarity.py                    Term-frequency cosine similarity — the Groundedness Checker's basis
    groundedness_checker.py           Groundedness Checker
    policy_engine.py                   NeMo Guardrails Policy Engine — the check orchestrator
    red_team.py                         Red-Team Self-Test Job
  db/                      SQLAlchemy 2.0 async models + repository
  clients/                 HTTP clients for LLM Gateway + Sentinel Agents
  security/                 Service-to-service JWT bearer auth (shared signing key), the entitlement gate, real OpenAPI security scheme declarations
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI router — check, policy-profiles, red-team-runs
  schemas/                    Pydantic request/response models
```

## Design notes vs. the LLD

- **Resiliency.** Every outbound HTTP call this module makes to a peer module goes through `ResilientHTTPClient` (`clients/resilience.py`): exponential-backoff retry on network errors and 5xx responses (never 4xx — a client error means the peer already processed the request and rejected it, so retrying just repeats the mistake), and a circuit breaker (`aiobreaker`) that opens after repeated failures so a struggling peer gets a break instead of a retry storm, and this module fails fast instead of piling up requests against a peer that's already down.

- **Policy engine.** The LLD calls for NVIDIA NeMo Guardrails as the
  policy execution engine. NeMo Guardrails' rails/flow DSL and its model
  runtime requirements are a large dependency footprint unsuited to this
  module's offline unit-test tier. `core/policy_engine.py` implements the
  same "orchestrate checks per policy profile" responsibility directly,
  in Python, against this module's own `PolicyProfile` config shape.
- **PII detection.** The LLD calls for Microsoft Presidio. Presidio pulls
  in spaCy language models (a multi-hundred-MB download on first use) —
  a network dependency this module's unit-test tier shouldn't carry.
  `core/pii_detector.py` implements regex/heuristic detection and
  redaction for the LLD's example entity types (EMAIL, PHONE_NUMBER,
  CREDIT_CARD, plus SSN) directly, plus a coarse capitalised-word-pair
  heuristic for PERSON — deliberately approximate (real named-entity
  recognition needs a real model), documented as such rather than
  silently claimed equivalent to Presidio's coverage.
- **Jailbreak/injection detection.** The LLD calls for "pattern
  detectors, a fine-tuned classifier, and an LLM Gateway call for
  ambiguous cases." The fine-tuned-classifier tier is replaced with a
  second, weaker pattern tier: strong patterns block immediately, weak
  signal words are ambiguous and deferred to the LLM Gateway fallback —
  preserving the LLD's layered-defence shape (multiple independent
  signals feeding one decision) without a trained model.
- **Groundedness checking.** The LLD calls for logic "shared...with
  Agentic RAG's Groundedness Critic." No shared library exists between
  modules in this build, so `core/groundedness_checker.py` is a parallel
  implementation of the same term-frequency-cosine-similarity approach
  Agentic RAG's Heuristic Groundedness Critic uses — the same idea, not
  literally shared code.
- **`context` field.** The LLD's documented `/check` request shape
  (`text, stage, policy_profile_id`) has no field for the context an
  output should be grounded against, which groundedness checking can't
  function without. `context` is accepted as an additional optional
  field.
- **Zero-config default profile.** The LLD's `/check` endpoint accepts an
  optional `policy_profile_id` but doesn't say what happens with none
  configured yet for a tenant. When omitted and no policy profile exists,
  this module falls back to an ephemeral profile built directly from its
  own YAML config defaults, so `/check` works immediately without
  requiring a `POST /policy-profiles` call first.
- **Postgres integration tests.** The repository layer is now also tested
  against a real Postgres (`tests/integration/`, opt-in via
  `TECTONIC_TEST_POSTGRES_URL` or Docker+testcontainers), covering JSONB
  round-tripping across `PolicyProfile`'s three list columns
  (`enabled_checks`, `pii_entity_types`, `denied_topics`), a real UUID foreign
  key (`BypassIncident.red_team_run_id`) scoping a multi-row query to only its
  parent run, and an `ORDER BY ... LIMIT 1` query across multiple candidate
  rows — none of which SQLite's unit-tier fakes can reliably prove. See
  `tests/integration/conftest.py` for how the Postgres instance is obtained.
  This tier's presence prompted a platform-wide sweep of every module's
  `db/models.py` for the same class of bug: `Mapped[datetime]` columns missing
  `DateTime(timezone=True)` despite the Alembic migration already defining
  them as timestamptz and the domain layer's defaults being tz-aware —
  invisible under SQLite, but a real correctness bug against Postgres once a
  domain default (or an explicit value) is written. Found and fixed here too.

- **Pagination on `GET /red-team-runs`.** Added `limit`/`offset` query
  params (default 50, max 200) and a `RedTeamRunListResponse` envelope
  (`items`/`total`/`limit`/`offset`) — this endpoint previously returned
  every matching row unbounded, a real scaling gap for a tenant with a
  large red-team run history. Ordered by `run_at` descending (newest run
  first) for stable pagination.

- **Connection pooling tuned to replica count.** SQLAlchemy's out-of-
  the-box defaults (`pool_size=5`, `max_overflow=10`) are the same
  regardless of how many pods are running — at this module's own
  `deploy/helm/guardrails/values.yaml` `autoscaling.maxReplicas: 30`,
  that's up to 450 connections to this module's own Postgres
  instance from this module alone at full autoscale, with no one having
  deliberately decided that number. `db/session.py`'s `make_engine` now
  passes explicit, configurable `pool_size=4` /
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
  `HTTPLLMGatewayClient` and `HTTPSentinelAgentsClient` make — a token
  minted to call one peer is rejected if replayed against a different
  one. The shared secret (`TECTONIC_JWT_SHARED_SECRET`, one Kubernetes
  Secret referenced by every module's Helm chart under this same literal
  env var name, not a per-module-prefixed one) defaults to an obviously-
  insecure placeholder for zero-config local dev/tests; `main.py` logs a
  startup warning if it's still active. This is service-to-service auth
  for inter-module calls, not the platform's external-facing user-auth
  story — a real API gateway/OAuth layer in front of the platform's own
  entry points is a separate, larger concern, out of scope here.

- **Enforces its own subscription entitlement via `EntitlementGateMiddleware`**
  (`security/entitlement_gate.py`) — see Agent Cards' README and the rollout
  playbook doc (`docs/entitlement-gate-rollout.md`) for the shared reference
  implementation. Layered after `ServiceAuthMiddleware` (authenticate, then
  entitle), it calls Multi-tenancy's real `GET /tenants/{id}/gate?module=guardrails`,
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

- **A real UUID for the synthesized default policy profile** (ticket
  #82's own Phase 2 support-agent slice, standing this module up against
  a real running Postgres for the first time for a tenant with no policy
  profile of its own yet) — `POST /v1/guardrails/check`'s own
  `_default_profile()` fallback (a real, in-memory, never-persisted
  stand-in used whenever a tenant hasn't created a profile) used the
  literal string `"default"` as its `id`. That's harmless against
  SQLite's own untyped `CHAR(36)` unit-test column, but a genuine
  `DataError` against a real Postgres UUID column once
  `create_intervention_log` tried to write it — invisible before because
  every prior test seeded a real profile first. Fixed to mint a real
  UUID per call instead (nothing needs to look this ephemeral profile up
  again by that id, unlike a real, persisted one) — see
  `tests/integration/test_check_route_postgres.py`.

- **NUL bytes/invalid enum values reaching the database or crashing
  unhandled** (ticket #82's platform-wide sweep, following the same bug
  a real CI run found on Multi-tenancy's and Billing and Metering's own
  contract tiers — see either module's own README for the original
  finding; this module wasn't in that sweep's original module list —
  found by re-grepping the whole platform for the same pattern once the
  sweep was otherwise done). `GET /red-team-runs`'s `tenant_id` never
  ran through a NUL-byte validator; fixed with
  `_reject_null_byte_query()`. `POST /check`'s own `stage` was a bare
  `str` on `CheckRequest`, hand-converted to `CheckStage` twice in the
  route body, raising an unhandled `ValueError` (500) for any
  non-member string — now typed `CheckStage` directly on the schema so
  FastAPI/Pydantic itself rejects an invalid value with a clean 422. No
  route-level test file existed for this module before this fix —
  `tests/unit/test_routes_guardrails.py` (new) pins just these
  regressions; comprehensive route coverage remains a real,
  separately-scoped gap.

## Running locally

```bash
uv venv && uv pip install -e ".[dev]"
pytest                                                    # unit tests, no external services needed

docker compose -f deploy/docker-compose.yml up --build    # full stack incl. Postgres, dependency-stub
```
