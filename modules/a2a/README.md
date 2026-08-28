# A2A — Module 22

The platform's standardised agent-to-agent delegation boundary: lets
this platform's own agents hand a task to another autonomous agent —
this platform's own or a genuinely external, cross-vendor one — and lets
external agents hand a task to this platform in return, both over the
A2A protocol. Full design doc:
[`../../docs/module-22-a2a.md`](../../docs/module-22-a2a.md).

## Layout

```
src/a2a_gateway/
  main.py                 FastAPI app, lifespan wiring, /healthz, /metrics, /.well-known/agent.json
  app_context.py           Process-wide dependency container
  config.py                  Pydantic Settings — LLD config schema
  core/
    domain.py                 A2ATaskRecord/A2AAccessPolicyRecord/AgentCard dataclasses, tolerant card parser
    ports.py                    Repository, peer client, Workflow Engine client
    fakes.py                     In-memory implementations of every port, for unit tests
    local_card.py                 Builds this platform's own published Agent Card from config
    access_policy_engine.py        Deny-by-default: is this external caller allowed this skill
    delegation_service.py           Outbound: card handshake, skill match, send, persist
    inbound_gateway.py               Inbound: policy check, dispatch into Workflow Engine
    rpc_gateway.py                    The `/v1/a2a/rpc` wire surface — message/send, tasks/get, tasks/cancel
  db/                      SQLAlchemy 2.0 async models + repository (A2ATask/A2AAccessPolicy/AgentCardCache)
  clients/                 a2a_peer_client.py (arbitrary external agents) + workflow_engine_client.py (platform peer)
  security/                 Service-to-service JWT bearer auth (shared signing key), the entitlement gate, real OpenAPI security scheme declarations
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI router — delegate, tasks, access-policies, rpc
  schemas/                    Pydantic request/response models
```

## Design notes vs. the LLD

- **Package named `a2a_gateway`, not `a2a`.** Same reasoning as MCP
  (Module 21) not naming its own package `mcp`: a real `a2a`/`a2a-sdk`
  Python package exists for the actual A2A protocol, and this module's
  own design notes point at that as a future swap-in for
  `clients/a2a_peer_client.py`. The module directory (`modules/a2a`)
  still matches the platform's one-directory-per-module convention.
- **Bidirectional, split cleanly by direction.** `DelegationService`
  (outbound: this platform calling another agent) and `InboundGateway`
  (inbound: another agent calling this platform) are two different
  classes with two different concerns — the only thing they share is the
  `A2ATaskRecord` they both write to, so a caller on either side polls
  the exact same `/v1/a2a/tasks/{id}` shape regardless of which
  direction created it.
- **Inbound dispatch is a real Workflow Engine (Module 1) call, not a
  second execution engine.** `InboundGateway.accept` maps the requested
  `skill_id` to a `definition_id` (via `skill_definition_map`) and calls
  Workflow Engine's own `POST /v1/workflow-engine/instances` — this
  module's job stops at accept/reject/track.
- **The skills this platform advertises and the skills it accepts are
  the same set, by construction.** `core/local_card.py`'s published
  Agent Card lists exactly the keys of `skill_definition_map` — there is
  no separate "advertised" list that could drift from what
  `InboundGateway` actually knows how to dispatch.
- **`/v1/a2a/rpc` is deliberately excluded from this platform's
  shared-secret JWT.** An external, third-party agent was never issued
  `TECTONIC_JWT_SHARED_SECRET` — that endpoint is instead gated by this
  module's own deny-by-default Access Policy Engine, keyed on a
  self-declared `X-A2A-Caller-Id` header. This is a real, intentional
  scoping decision for this first version, not an oversight: a
  self-declared caller id paired with a policy row is weaker than a
  signed credential per-caller, and a future version should replace it
  with real per-caller credentials (e.g. mTLS or a per-partner API key)
  once this platform has genuine external A2A partners to onboard — the
  Access Policy Engine's own shape (deny-by-default, one row per
  `(caller_agent_id, tenant_id)`) does not need to change to support that,
  only how `caller_agent_id` gets authenticated does.
- **`/.well-known/agent.json` lives at the app root, not under
  `/v1/a2a/*`.** Per the A2A spec's own well-known-endpoint convention —
  discovery has to work before a caller has any credential or knows this
  module's own API prefix.
- **Outbound delegation is a one-shot send in this first version, not a
  background re-polling loop.** `DelegationService.delegate` sends the
  task and records whatever status the peer's own `message/send`
  response carries immediately; it does not keep re-calling the peer's
  `tasks/get` in the background to advance a `working` task to
  `completed` on its own. A caller polls this module's own
  `/v1/a2a/tasks/{id}` for whatever was last recorded — a real
  limitation worth being explicit about, matching this platform's
  convention of documenting a scoping decision rather than silently
  under-delivering the spec (see Observability, Module 19's own "one
  remaining deviation" for the same kind of honest scoping note).
- **`MCPBackendHTTPClient`'s per-target-URL circuit breaker pattern,
  applied here as `A2APeerHTTPClient`.** Calling a different absolute
  URL per target agent on one shared `httpx.AsyncClient` needs its own
  breaker per URL (`_breaker_for`), the identical shape of problem MCP
  (Module 21) already solved for calling a different registered server
  per request.
- **Connection pooling and pagination, built in from day one.** Sized
  against this module's own Helm chart's `autoscaling.maxReplicas` from
  the start (this platform's standard formula), and `GET /tasks` is
  paginated (`limit`/`offset`, default 50/max 200) from its first
  version.

- **Enforces its own subscription entitlement via `EntitlementGateMiddleware`**
  (`security/entitlement_gate.py`) — see Agent Cards' README and the rollout
  playbook doc (`docs/entitlement-gate-rollout.md`) for the shared reference
  implementation. Layered after `ServiceAuthMiddleware` (authenticate, then
  entitle), it calls Multi-tenancy's real `GET /tenants/{id}/gate?module=a2a`,
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
