# MCP — Module 21

The platform's single, governed entry point for MCP (Model Context
Protocol) traffic: a registry of MCP servers (the "internal server
marketplace"), a per-tenant/per-tool access policy over that registry,
and a JSON-RPC 2.0 proxy that enforces the policy before forwarding a
request to the real backing server. Full design doc:
[`../../docs/module-21-mcp.md`](../../docs/module-21-mcp.md).

## Layout

```
src/mcp_gateway/
  main.py                 FastAPI app, lifespan wiring, /healthz, /metrics
  app_context.py           Process-wide dependency container
  config.py                  Pydantic Settings — LLD config schema
  core/
    domain.py                 McpServerRecord/McpToolRecord/AccessPolicyRecord dataclasses
    ports.py                    Repository, MCP backend client
    fakes.py                     In-memory implementations of every port, for unit tests
    registry_service.py           Registry Service — the marketplace CRUD
    access_policy_engine.py        Access Policy Engine — deny-by-default authorization
    rpc_gateway.py                  RPC Gateway — enforce + forward a JSON-RPC request
    capability_sync_service.py       Capability Sync Service — refresh a server's cached tools/list
  db/                      SQLAlchemy 2.0 async models + repository (McpServer/McpTool/AccessPolicy)
  clients/                 Resilient JSON-RPC-over-HTTP client to arbitrary registered servers
  security/                 Service-to-service JWT bearer auth (shared signing key), the entitlement gate, real OpenAPI security scheme declarations
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI router — register, discover, sync, access-policy, rpc
  schemas/                    Pydantic request/response models
```

## Design notes vs. the LLD

- **Package named `mcp_gateway`, not `mcp`.** The LLD names the official
  `mcp` Python SDK as MCP's own implementation. Deliberately not reusing
  that name for this module's own Python package: it would shadow the
  real `mcp` PyPI package's import path, which this module's own design
  notes point at as a future swap-in for `clients/mcp_backend_client.py`.
  The module directory (`modules/mcp`) still matches the platform's
  one-directory-per-module convention.
- **Distinct from Tool Orchestration's `HTTPMCPClientAdapter`.** Module 4
  already has its own generic JSON-RPC-2.0-over-HTTP client for calling
  whatever MCP server a specific `ToolDefinition.mcp_server_ref` names —
  a direct, ungoverned, one-caller-to-one-known-server relationship. This
  module is the opposite direction: the place a server gets *registered*
  so any caller platform-wide can discover and be governed calling it.
  Tool Orchestration is a natural (optional) caller of this module once a
  tool is MCP-registered here rather than pointed at directly; the two
  are not redundant.
- **Deny-by-default access policy, enforced before every forward.** A
  tenant with no `AccessPolicyRecord` row for a server has zero access —
  `core/access_policy_engine.py` never treats "no policy" as "allow."
  Where a policy row does exist, `tools/call` gets an additional check
  against its `allowed_tools` allow-list (`null` = every tool on this
  server; every other JSON-RPC method only needs the server-level row to
  exist, since `tools/call` is the one method that actually executes
  something).
- **A denied request returns a JSON-RPC error, not just an HTTP error.**
  `RpcGateway.handle` catches `AccessDeniedError` and returns a normal
  `200` response with a JSON-RPC `error` object (code `-32001`) rather
  than an HTTP 4xx — a caller speaking JSON-RPC gets a JSON-RPC-shaped
  answer either way, consistent with how the protocol itself represents
  method-level failures.
- **`MCPBackendHTTPClient` is not a `ResilientHTTPClient` subclass.**
  That base class assumes one fixed `base_url` per client instance,
  while this module calls a different absolute URL per registered server
  on a single shared `httpx.AsyncClient` — the same shape of problem LLM
  Gateway's `HTTPProviderClient` already solved for calling a different
  provider endpoint per request, and the same answer: each server gets
  its own circuit breaker (`_breaker_for`), so one struggling MCP server
  never trips requests to a different one.
- **Service-to-service JWT auth, inbound only.** `security/jwt_auth.py`
  adds shared-signing-key (HS256) bearer auth: `ServiceAuthMiddleware`
  verifies every inbound request's `Authorization: Bearer <JWT>` against
  this module's own `service_name` as the required audience (except
  `/healthz` and `/metrics`). This module has no platform-peer outbound
  dependency to wrap in `ServiceBearerAuth` — its one outbound call
  target is an arbitrary registered MCP server, deliberately excluded
  from this platform's shared-secret trust boundary for the same reason
  Tool Orchestration's own MCP client is (see
  `clients/mcp_backend_client.py`). The shared secret
  (`TECTONIC_JWT_SHARED_SECRET`, one Kubernetes Secret referenced by
  every module's Helm chart under this same literal env var name)
  defaults to an obviously-insecure placeholder for zero-config local
  dev/tests; `main.py` logs a startup warning if it's still active.
- **Connection pooling and pagination, built in from day one.** Sized
  against this module's own Helm chart's `autoscaling.maxReplicas` from
  the start (this platform's standard formula), and `GET /servers` is
  paginated (`limit`/`offset`, default 50/max 200) from its first
  version — unlike the 19 modules built before the platform's
  enterprise-readiness remediation series, this module never had
  un-tuned defaults to fix.

- **Enforces its own subscription entitlement via `EntitlementGateMiddleware`**
  (`security/entitlement_gate.py`) — see Agent Cards' README and the rollout
  playbook doc (`docs/entitlement-gate-rollout.md`) for the shared reference
  implementation. Layered after `ServiceAuthMiddleware` (authenticate, then
  entitle), it calls Multi-tenancy's real `GET /tenants/{id}/gate?module=mcp`,
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
