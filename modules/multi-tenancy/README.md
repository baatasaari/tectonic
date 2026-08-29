# Multi-tenancy — Module 30

The platform's tenant registry and isolation-verification layer: every
tenant's lifecycle (`active`/`suspended`/`deleted`) is governed here,
and a real, executable probe periodically confirms that a tenant-scoped
query against any registered platform module actually returns only
that tenant's own records. Full design doc:
[`../../docs/module-30-multi-tenancy.md`](../../docs/module-30-multi-tenancy.md).

## Layout

```
src/multi_tenancy/
  main.py                 FastAPI app, lifespan wiring, /healthz, /metrics
  app_context.py           Process-wide dependency container
  config.py                  Pydantic Settings — LLD config schema, incl. probe_targets
  core/
    domain.py                 TenantRecord/IsolationProbeResult, Organisation/Workspace/Environment, QuotaSet/ResourceAllocation, the lifecycle state machines
    ports.py                    Repository, the Auditability client, the one generic tenant-scoped list client shape
    fakes.py                     In-memory implementations of every port, for unit tests
    tenant_registry_service.py    Tenant Registry — register/suspend/reactivate/delete, the gate check
    organisation_service.py        Organisation Service — top of the platform hierarchy control plane
    workspace_service.py            Workspace Service — always scoped to one tenant
    environment_service.py           Environment Service — always scoped to one workspace
    quota_service.py                  Quota Set management + real-time QuotaEnforcementService
    residency_policy_service.py        Residency Policy CRUD — enforcement lives in EnvironmentService.register
    resource_allocation_service.py      Resource Allocation Service — request/approve/reject
    isolation_probe_service.py           Isolation Probe Service — the real, executable isolation check
  db/                      SQLAlchemy 2.0 async models + repository (Tenant/Organisation/Workspace/Environment/QuotaSet/ResidencyPolicy/ResourceAllocation/IsolationProbeResult)
  clients/                 Resilient HTTP clients: Auditability, and the one reused against every registered probe target
  security/                 Service-to-service JWT bearer auth (shared signing key), real OpenAPI security scheme declarations
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI router — tenant lifecycle, gate, isolation probes, the hierarchy control plane
  schemas/                    Pydantic request/response models
```

## Design notes vs. the LLD

- **Isolation is actively verified, not just assumed.** Every module in
  this platform already follows one identical list-endpoint contract —
  `GET .../resource?tenant_id=X` → `{"items": [...each with its own
  tenant_id...]}`. `IsolationProbeService` exploits that directly: it
  calls a target module's real list endpoint scoped to one tenant and
  checks that every returned item's own `tenant_id` actually matches —
  a genuine, executable check, no per-module adapter code needed.
- **The LLD's own key metric is a real, wired counter.**
  `multi_tenancy_isolation_breach_incidents_total` increments by the
  actual number of foreign records a probe run found.
- **Fails closed.** A probe against an unreachable target is recorded
  `passed=False` with a `probe_unavailable` reason — never a silent
  assumed-fine.
- **A real state machine for tenant lifecycle**, the same shape Agent
  Marketplace, LLMOps, Deployment Strategy and PromptOps already
  established: `active ↔ suspended`, either → `delete` (terminal).
  `GET /tenants/{id}/gate` is the one real integration point every
  other module's request path should call before serving a request.
- **Per-tenant module entitlements: the platform's feature-flag store.**
  `POST /tenants/{id}/entitlements` wholesale-replaces the set of module
  names a tenant's subscription plan currently includes (never a
  field-by-field patch — a plan change fully re-derives the flag set, so
  no stale flag survives a downgrade); `GET /tenants/{id}/entitlements`
  reads it back as `{tenant_id, module_names, configured}`.
  `GET /tenants/{id}/gate?module=<name>` now also denies when `module`
  isn't in that set. A tenant that has never had entitlements set is
  **ungated** — every module allowed — a deliberate rollout-safety
  default (`configured: false`) so shipping this check never silently
  starts denying tenants that predate it; an explicit *empty* entitlement
  set (`configured: true`, zero modules) is a real, different state that
  denies everything. See `TenantRecord.entitlements_configured_at`'s
  docstring in `core/domain.py` for the full reasoning. Billing and
  Metering syncs to this whenever a tenant's pricing plan changes; any
  module wanting to enforce its own entitlement should call
  `gate(tenant_id, module=<its own service name>)` before serving a
  request, via an `EntitlementGateMiddleware` layered after service auth
  (Agent Cards carries the reference implementation — see its README).
  That middleware must fail **open** (allow, with a loud warning log) if
  this module is unreachable: a commercial/entitlement gate must never
  become a platform-wide outage vector the way a zero-trust auth check
  correctly does fail closed.
- **The platform hierarchy control plane** (independent architecture
  assessment §3.1): `Organisation -> Tenant -> Workspace -> Environment`,
  each with its own register/suspend/reactivate/delete lifecycle
  (`/v1/multi-tenancy/organisations`, `/workspaces`, `/environments`),
  real Auditability events on every create and status transition
  (`organisation_created`/`_status_changed`, same for `workspace_*` and
  `environment_*`; `tenant_created`/`_status_changed` too — Multi-tenancy
  didn't previously call Auditability for its own tenant lifecycle at
  all, a real gap fixed alongside adding the three new levels), and an
  `owner_identity_id`/`labels`/`version` field on every one of the new
  resources. An Organisation is optional — most tenants in this
  platform's own test data have no need of one — set via
  `TenantRecord.organisation_id`, nullable, a real valid state rather
  than an oversight. A Workspace always belongs to exactly one tenant, an
  Environment to exactly one workspace; both validate their parent
  exists at registration (`TenantNotFoundError`/`WorkspaceNotFoundError`)
  the same way `set_entitlements` already validates its own tenant.
  **Cascading offboarding is real** (Phase 2 closed this): a Tenant's
  `suspend()`/`delete()` cascade to every descendant Workspace and,
  transitively, every descendant Environment —
  `TenantRegistryService._cascade` walks that tenant's own workspaces
  (paginated, not one unbounded list call), and `WorkspaceService.
  suspend()`/`.delete()` themselves cascade one level further down to
  their own Environments via `cascade_environments`, so a workspace
  suspended/deleted directly (not only via a tenant-level cascade) also
  correctly carries its environments with it. Idempotent throughout:
  `is_legal_hierarchy_transition` skips a child already at (or past)
  the target status rather than raising, so re-running a cascade after
  a partial failure converges instead of erroring on work already
  done, and a real audit event is emitted for every cascaded
  transition, not just the root. `reactivate()` deliberately does not
  cascade at either level — an operator's own independent suspension
  of a child resource must survive its parent reactivating. Organisation
  → Tenant cascading remains separate, unbuilt work (see
  `OrganisationService.delete`'s own docstring).
  **Optimistic-concurrency enforcement is real too** (Phase 2 also
  closed this): every mutating Organisation/Workspace/Environment/
  ResourceAllocation endpoint now requires the caller's
  `expected_version`, checked by a real `UPDATE ... WHERE id = :id AND
  version = :expected_version` at the repository layer
  (`SQLAlchemyMultiTenancyRepository._compare_and_swap`) — a stale
  version raises a real `OptimisticConcurrencyError` (409), not a
  silent overwrite. `TenantRecord` deliberately has no `version` field
  and stays out of scope here (see `core/domain.py`'s own note on why
  it's kept separate from the other four). Proven under real
  concurrent callers against real Postgres
  (`tests/integration/test_optimistic_concurrency_postgres.py`): ten
  simultaneous callers racing to suspend the same Organisation
  converge to exactly one winner and nine real conflicts, and two
  reviewers racing to approve/reject the same ResourceAllocation land
  exactly one decision.
  **Residency-policy enforcement is real too** (Phase 2 also closed
  this): a per-tenant `ResidencyPolicy` (`allowed_regions`, wholesale-
  replaced the same way `QuotaSet`/entitlements already are) is now
  enforced for real at `EnvironmentService.register` — a `region`
  outside the policy raises `ResidencyPolicyViolationError` (a real
  `422`), not a silently-accepted label. An unconfigured tenant is
  unrestricted (the same rollout-safety default `QuotaSet`/
  entitlements already establish), and an explicit empty
  `allowed_regions` is a real, meaningful "no region permitted" policy,
  distinct from never having configured one. Exposed for other modules
  to query before provisioning a region-specific resource via `GET/POST
  /tenants/{id}/residency-policy`, the same shape `quota-set` already
  uses. **What this still deliberately does not do yet**: no other
  module has adopted `environment_id` scoping yet (Agent Applications —
  Workflow Engine runs, Conversational Engine sessions — are still
  tenant-scoped only), so nothing downstream of Environment
  registration re-checks residency before actually placing data.
- **Quota Set and Resource Allocation** (independent architecture
  assessment §5.2 "Resource allocation and quota change"): the
  remaining two legs of the assessment's own canonical resource chain
  (`... -> Entitlement Set -> Quota Set -> ... -> Resource Allocation`).
  A `QuotaSet` is one tenant's resource-class limits
  (`POST/GET /tenants/{id}/quota-set`, a wholesale replace like
  entitlements — never a field-by-field patch); an unconfigured tenant
  is unlimited, the same rollout-safety default entitlements already
  established. `POST /tenants/{id}/quota/check` is the real-time
  decision every module wanting to enforce a quota before doing
  expensive work is meant to call — the quota analogue of `gate()`.
  Two enforcement shapes, chosen by resource-class name convention
  (`_per_minute`/`_per_second`/`_per_hour`/`_per_day`/`_daily` suffix
  vs. everything else): **rate-shaped** classes (`requests_per_minute`,
  `tokens_per_minute`, ...) get a real, atomic, fixed-window counter
  this module owns outright (`quota_counters` table, a genuine
  `INSERT ... ON CONFLICT DO UPDATE ... RETURNING`, correct under
  concurrent callers — verified against real Postgres, not just
  SQLite fakes); **capacity-shaped** classes (`storage_gb`,
  `vector_count`, ...) are a stateless ceiling check against
  `current_usage` the caller reports, since the owning module (Vector
  DB for `vector_count`, etc.) is the real source of truth for its own
  usage, the same don't-duplicate-another-module's-state posture
  FinOps already takes reading Billing's real spend. A
  `ResourceAllocation` is the assessment's own "canonical allocation
  object" (CPU/memory/GPU, replicas, concurrent runs, requests/tokens
  per minute, model spend, workflow concurrency, storage, vector
  count, ingestion volume, retention, ..., kept as a flexible
  `resources` dict rather than one field per dimension) scoped to one
  Environment, with a real request -> automated-or-manual-approval ->
  active lifecycle (`POST /resource-allocations`, `.../approve`,
  `.../reject`): a request that changes every resource class by no
  more than 20% of its current active value auto-approves immediately;
  a brand-new resource class, or a bigger jump, needs an explicit human
  `approve`. **What this deliberately does not do yet**: reconcile the
  approved numbers against real Kubernetes/database/vector capacity, a
  real regional capacity check, or a real billing amendment — this
  module owns the *approved intent*, not enforcement against live
  infrastructure (nor does any other module yet call `quota/check`
  before doing work — this ships the real, tested capability other
  modules are meant to adopt next, the same "reference implementation
  first, rollout second" shape `EntitlementGateMiddleware` used); and a
  stale `quota_counters` row for a window that's long past is never
  cleaned up — a real TTL/GC job for old windows is separate, unbuilt
  work.

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
