# Agent Cards — Module 23

The platform's trust-scored discovery registry for Agent Cards: any
agent gets a published, machine-readable capability manifest here, and
any orchestrator platform-wide can search that registry by skill and get
results ranked by a genuine, cross-module trust signal. Full design doc:
[`../../docs/module-23-agent-cards.md`](../../docs/module-23-agent-cards.md).

## Layout

```
src/agent_cards/
  main.py                 FastAPI app, lifespan wiring, /healthz, /metrics
  app_context.py           Process-wide dependency container
  config.py                  Pydantic Settings — LLD config schema
  core/
    domain.py                 AgentCardRecord/TrustScoreBreakdown dataclasses
    ports.py                    Repository, Evaluation Framework client, Regulatory Compliance client
    fakes.py                     In-memory implementations of every port, for unit tests
    registry_service.py           Registry Service — card CRUD
    discovery_service.py           Discovery Service — search + is_stale
    trust_score_calculator.py       Trust Score Calculator — weighted real-peer signals
  db/                      SQLAlchemy 2.0 async models + repository (AgentCard)
  clients/                 Resilient HTTP clients to Evaluation Framework + Regulatory Compliance
  security/                 Service-to-service JWT bearer auth (shared signing key), the entitlement gate, real OpenAPI security scheme declarations
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI router — register, discover, update, recompute-trust-score
  schemas/                    Pydantic request/response models
```

## Design notes vs. the LLD

- **Trust score reads two real peers, never fabricates a placeholder.**
  `TrustScoreCalculator` calls Evaluation Framework's own `GET /scores`
  (per-agent metric-score history) and Regulatory Compliance's own `GET
  /coverage` (per-tenant control-coverage percentage) — the same "real
  peer, not a guessed shape" pattern this platform already established
  for Observability's Cost Attribution Joiner and Auditability's
  NL-query LLM Gateway call. A component with no data is excluded from
  the weighted average, not defaulted to a fake neutral 0.5 — and if
  neither peer has data, `trust_score` stays `null`.
- **A slow or down peer degrades gracefully, one signal at a time.**
  Each peer call is wrapped independently (`TrustScoreCalculator._safe_call`):
  a compliance peer that's unreachable (retries + circuit breaker
  exhausted) still leaves a performance-only trust score computable,
  logged at `warning`, rather than failing the whole recompute over one
  unavailable signal.
- **Distinct from A2A (Module 22)'s own card handling.** A2A's
  `core/local_card.py` publishes *this platform's own* one card at
  `/.well-known/agent.json`, and its `DelegationService` caches *one
  target's* card for the duration of a single delegation handshake —
  both scoped to A2A's own protocol mechanics. This module is the
  platform-wide, governed, trust-scored catalogue a discovery *search*
  runs against — the same registry/direct-call split already drawn
  between MCP (Module 21, registry) and Tool Orchestration (Module 4,
  direct call).
- **JSONB containment for the skill filter, Postgres-only.**
  `GET /agent-cards?skill_id=...` filters via `skills @> [{"id": ...}]`
  — true when some element of the `skills` JSONB array has at least that
  key/value, without requiring an exact full-object match. This path is
  exercised for real in the integration tier; the SQLite-backed unit
  tier's `InMemoryAgentCardsRepository` implements the identical filter
  semantics in pure Python instead, since SQLite has no JSONB
  containment operator.
- **Discovery ranks by trust score, not registration order.** Both the
  real repository (`ORDER BY trust_score DESC NULLS LAST`) and the
  in-memory fake sort results the same way — a card with no score yet
  sorts after every scored card, not before (which would make an
  unscored card look untrustworthy) or randomly.
- **Connection pooling and pagination, built in from day one.** Sized
  against this module's own Helm chart's `autoscaling.maxReplicas` from
  the start (this platform's standard formula), and `GET /agent-cards`
  is paginated (`limit`/`offset`, default 50/max 200) from its first
  version.
- **This module carries the platform's reference `EntitlementGateMiddleware`**
  (`security/entitlement_gate.py`) — the per-module feature-flag check
  every selectable module is meant to adopt (see the rollout playbook
  doc, `docs/entitlement-gate-rollout.md`). Layered after
  `ServiceAuthMiddleware` (authenticate, then entitle), it reads
  `X-Tenant-Id` off the request and calls Multi-tenancy's real `GET
  /tenants/{id}/gate?module=agent-cards`, denying with `402 Payment
  Required` when the tenant's subscription doesn't include this module.
  It **fails open** if Multi-tenancy is unreachable — a deliberate
  contrast with `ServiceAuthMiddleware`'s zero-trust fail-closed
  posture: a commercial/entitlement gate must never become a
  platform-wide outage vector. A short in-process TTL cache plus a
  circuit breaker bound both the added load on Multi-tenancy and the
  added latency here during a real outage.

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
  unvalidated** (ticket #82's platform-wide sweep, following the same
  bug a real CI run found on Multi-tenancy's and Billing and Metering's
  own contract tiers — see either module's own README for the original
  finding). `GET /agent-cards`'s `tenant_id`/`skill_id` never ran through
  a NUL-byte validator; fixed with `_reject_null_byte_query()`.

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
