# Session Handoff

Prepared 2026-08-29 for a clean handover to a new Claude Code session. This
file is a point-in-time snapshot; durable, every-session conventions live in
`CLAUDE.md` instead — read that first, then this.

## 1. Project Objective

Tectonic is a 34-module "Agentic AI Platform" being built module-by-module
against low-level design specs in `docs/module-NN-*.md`, tracked against
`docs/agentic-platform-final-module-table.md`. Work proceeds in tickets: a
"Phase 1 kernel" pass closed cross-cutting platform gaps (auth, entitlements,
observability, supply chain, etc.). Phase 2 moved into real product slices;
the first is a tenant support agent, designed in
`docs/phase2-product-slice-01-support-agent.md` and — as of this session —
**built and verified end-to-end against real running module instances**
(ticket #82).

## 2. Current Architecture

Each module under `modules/<name>/` is an independently deployable FastAPI
service: async SQLAlchemy + its own Postgres schema (Alembic migrations),
`ServiceAuthMiddleware` (service-to-service JWT) + `EntitlementGateMiddleware`
on every non-Platform-Base module, OpenTelemetry tracing, Prometheus
`/metrics`, its own Helm chart under `deploy/helm/`. Modules call each other
over real HTTP with resilient clients (`ResilientHTTPClient` — circuit
breaker via `aiobreaker`), never in-process imports of a peer's code.

New this session: **`tests/product-slices/`**, a deliberate, narrow
exception to every module's own single-module test tiers — it stands up an
entire live multi-process stack (15 modules + a small mock external-systems
stub) and drives real conversations across all of them. See its own README.

Full architectural detail is in each module's own README and LLD doc — this
section is deliberately not a re-derivation of those.

## 3. Repository Structure

```
docs/                       Low-level design specs, module table, Phase 2 slice design
modules/<name>/             34 independently-deployable services (src/, tests/, deploy/,
                            pyproject.toml, README.md — see CLAUDE.md for the workflow)
scripts/                    seed_subscription_tiers.py, seed_support_agent_demo.py,
                            post_support_agent_definition.py, product-slice-stubs/
                            (stack.py orchestrator, external_mocks.py, smoke_test.py)
tests/product-slices/       NEW this session: cross-module e2e test tier (its own
                            pyproject.toml/README, not a modules/<name>/ package)
test-data/                  subscription-tiers/ fixture JSON used by seeding scripts
.github/workflows/ci.yml    Per-module lint+test matrix, SBOM+sign, gate job
                            (tests/product-slices/ is NOT wired into CI yet — real,
                            tracked follow-up, see §7)
README.md                   Long running narrative of every ticket's design decisions
CLAUDE.md                   Durable, every-session instructions
SESSION_HANDOFF.md          This file
```

## 4. Work Completed (this session — ticket #82)

Built and verified the Phase 2 support-agent slice end-to-end against real,
live module instances (no Docker in this sandbox — every module runs as a
real `uvicorn` process against its own real per-module Postgres via
`scripts/product-slice-stubs/stack.py`). All three of the design doc's
scripted conversations pass for real; the refund scenario's real escalation
reaches Human Oversight's real queue and a real reviewer decision resumes
the conversation; Auditability shows a real hash-chained trail; Billing and
Metering shows real non-zero usage. Full narrative (every fix, every gap
found) is in root `README.md`'s Phase 2 section and in each touched
module's own README — not duplicated here. Touched modules: Workflow
Engine, Multi-tenancy, Billing and Metering, LLM Gateway, Vector DB,
Knowledge Base, Tool Orchestration, Conversational Engine, Agentic RAG,
Guardrails. New: `tests/product-slices/` (the one net-new automated test
tier this ticket adds), `scripts/seed_support_agent_demo.py`,
`scripts/post_support_agent_definition.py`,
`scripts/product-slice-stubs/{stack.py,external_mocks.py,smoke_test.py}`.

Committed and pushed to `claude/practical-wozniak-l1723c-rw7pp0`
(commit `4d7197c`, on top of `75a5439`).

## 5. Files Changed

See `git show --stat 4d7197c` for the exact diff (54 files). Summary: one
real wire-shape fix or missing-endpoint fix per touched module (each
module's own README documents its own fix in full); `KafkaEventPublisher`'s
half-initialized-producer hang fixed in both Workflow Engine and
Multi-tenancy; Conversational Engine's real `WorkflowEngineClient` +
`resume_from_workflow` addition; `tests/product-slices/` (new); root
`README.md` updated.

## 6. Current Application State

`git status`: clean, branch `claude/practical-wozniak-l1723c-rw7pp0`, pushed
and up to date with `origin/claude/practical-wozniak-l1723c-rw7pp0` at
commit `4d7197c`. All 10 touched modules' full suites (ruff + unit +
integration + contract where present) re-verified green after every fix
(see §10). `tests/product-slices/` itself passes 8/8 (6 support-agent
scenarios + 2 trace-propagation regression tests) from a clean venv, stack
up, and stack down. No live module processes left running; local Postgres
16 and Redis are up (both needed a restart mid-session after a container
restart — see §8).

## 7. Incomplete Work

- ~~`tests/product-slices/` is not wired into CI~~ — **done, later in this
  same session**: `.github/workflows/ci.yml`'s own `product-slice-support-agent`
  job runs it as a required check on every push/PR to `claude/**`, its own
  `postgres:16-alpine`/`redis:7-alpine` service containers, building all
  15 modules' own venvs first. `scripts/product-slice-stubs/stack.py`'s
  own Postgres connection is now env-overridable
  (`TECTONIC_STACK_POSTGRES_{HOST,PORT,USER,PASSWORD}`) for this — CI's
  service container uses different credentials than this sandbox's own
  local dev Postgres — and it gained a real `ensure_databases()` step
  (idempotent) since a fresh CI Postgres container starts with none of
  this slice's 15 databases yet. See `tests/product-slices/README.md`'s
  own "In CI" section.
- **Observability's own real store isn't exercised.** Trace-propagation
  verification is deliberately scoped to proving W3C `traceparent`
  continuity across one real HTTP hop (`test_trace_propagation.py`), not
  spans landing in Observability's real store — no real OTel
  Collector/Tempo is available in this sandbox. Documented in that test's
  own docstring and in root README's Phase 2 section.
- **A demo front-end / SDK-and-Developer-Portal exercise** — explicitly
  out of this slice's scope per the design doc's own "What this slice
  deliberately does not cover" section; unchanged this session.
- **Agentic RAG's hybrid retrieval fan-out (Graph DB, Knowledge Base's own
  symbolic lookup) is disabled**, not fixed, for this slice
  (`AGENTIC_RAG_RETRIEVAL__HYBRID_RETRIEVAL_ENABLED=false` in
  `stack.py`): Graph DB is legitimately out of this slice's scope, and
  Knowledge Base has no real symbolic-lookup endpoint at all yet — a real,
  separately-scoped gap (`HTTPGraphDBClient`/`HTTPKnowledgeBaseClient` in
  Agentic RAG still carry their own pre-existing invented wire shapes,
  unexercised and unfixed by this ticket).
- Everything named in the prior handoff's own backlog (rolling the quota
  pre-flight/event-outbox/contract-test patterns out to the platform's
  remaining ~29 modules; Organisation → Tenant cascading offboarding is
  actually now built per a later commit — re-check `git log` rather than
  trusting this line) is unchanged by this session and still open.

## 8. Known Issues

- **This sandbox's own local Postgres never actually validates real
  GitHub Actions CI** -- ticket #82's own earlier work (before the CI
  job existed) was verified thoroughly against this sandbox's own local
  Postgres/Redis, but the branch's *real* CI runs (checked only once the
  new `product-slice-support-agent` job's own push triggered a look at
  them) had been failing since the very first ticket #82 commit, on two
  modules this sandbox's own local runs never caught: a real, GitHub-
  Actions-only-reproducible Hypothesis fuzzing seed found a NUL-byte-in-
  a-raw-`Query()`-parameter bug (see §12's own P1 item) that this
  sandbox's own local Postgres/seed never happened to hit. **Check the
  branch's actual GitHub Actions run after any push that touches a
  module with a `tests/contract/` tier** (`list_workflow_runs` for
  `ci.yml` on this branch) rather than trusting a local-only green as
  the final word -- this sandbox's own Postgres/Hypothesis state isn't
  identical to a fresh GitHub Actions runner's.
- **Postgres and Redis are not durable across a container restart in this
  sandbox**, despite `CLAUDE.md`'s own claim that the Postgres password
  persists — both had to be restarted mid-session
  (`sudo pg_ctlcluster 16 main start`;
  `redis-server --daemonize yes --port 6379 --save "" --appendonly no`)
  and the Postgres password re-set once
  (`ALTER USER postgres PASSWORD 'postgres'`). Check both are actually up
  before trusting a "connection refused" as a real bug.
- **A leftover live product-slice stack breaks unrelated modules' own
  contract tests.** Diagnosed this session: multi-tenancy's contract test
  failed with `RuntimeError: Event loop is closed` only because a
  previous manual `stack.py` run was still running underneath it — its
  real HTTP clients (Auditability, probe targets) found a real peer
  instead of the no-op/stub the contract fixture expects, and a pooled
  connection reused across schemathesis's fresh-event-loop-per-call
  pattern is exactly `CLAUDE.md`'s own documented bug class, just on an
  HTTP client pool instead of a DB engine pool. **Always confirm no
  `stack.py`-launched processes are still running (`ps aux | grep
  uvicorn`) before trusting any one module's own contract-test result.**
  `tests/product-slices/conftest.py`'s own `live_stack` fixture tears
  itself down in a `finally` for exactly this reason.
- Deprecation warnings (non-blocking, pre-existing): `aiobreaker`'s
  internal use of `datetime.utcnow()`, an Alembic `path_separator` config
  warning, harmless "Failed to export traces to localhost:4317" OTLP
  noise (no collector in this sandbox) — all cosmetic, not introduced
  this session.
- No known regressions from this session's work — every touched module's
  full suite re-run clean (§10).

## 9. Decisions and Constraints

- **No secrets in this repo.** Only the sandbox's own well-known local dev
  Postgres password (`postgres`/`postgres` on `localhost:5432`) and the
  platform-wide insecure default JWT shared secret
  (`dev-insecure-shared-secret-change-me`) appear anywhere — neither is a
  production credential.
- **Real infrastructure over mocks**, reinforced again this session: the
  only mocked piece anywhere in the support-agent slice is
  `scripts/product-slice-stubs/external_mocks.py`, standing in for exactly
  two things genuinely outside this platform's own 34 modules (an LLM
  provider, a merchant's order-status backend) — every module-to-module
  call is real.
- **Kafka is confirmed not required for this slice's critical path** — the
  outbox pattern is fire-and-forget by design, and no module in this
  platform runs a real Kafka consumer yet. This was checked and confirmed
  (with the user) before any ticket #82 code was written; not re-litigate
  this without new evidence.
- **Tracing verification is deliberately scoped down** (agreed with the
  user before building): prove real cross-process W3C `traceparent`
  propagation, not spans landing in Observability's real store (no real
  OTel Collector/Tempo available here).
- **The CE→WE integration was built for real**, not stubbed around (agreed
  with the user before building): Conversational Engine now has a real
  `WorkflowEngineClient`, gated behind `settings.workflow_routing.enabled`
  (default off) so every pre-existing direct-LLM-Gateway deployment is
  unaffected.

## 10. Tests and Validation

Re-run for real this session (not assumed from memory), all green, after
every fix and after a Postgres/Redis restart mid-session:

| Module | ruff | unit | integration | contract |
|---|---|---|---|---|
| workflow-engine | clean | 78 passed | 7 passed | 1 passed |
| multi-tenancy | clean | 174 passed | 19 passed | 1 passed |
| billing-and-metering | clean | 75 passed | 10 passed | 1 passed |
| llm-gateway | clean | 74 passed | 4 passed | 1 passed |
| vector-db | clean | 61 passed | 3 passed | 1 passed |
| knowledge-base | clean | 70 passed | 4 passed | (no contract tier) |
| tool-orchestration | clean | 57 passed | 3 passed | (no contract tier) |
| conversational-engine | clean | 59 passed | 4 passed | (no contract tier) |
| agentic-rag | clean | 48 passed | 3 passed | (no contract tier) |
| guardrails | clean | 58 passed | 4 passed | (no contract tier) |

Plus `tests/product-slices/`: **8 passed** (6 support-agent scenarios + 2
trace-propagation), full stack up→seed→test→down cycle, run twice from a
freshly rebuilt venv to confirm it's not an artifact of leftover state.

Commands used (per module, from `modules/<name>/`):
```bash
source .venv/bin/activate   # after uv venv && uv pip install -e ".[dev]"
ruff check src tests
pytest tests/unit -v
TECTONIC_TEST_POSTGRES_URL=postgresql://postgres:postgres@localhost:5432/postgres pytest tests/integration -v
TECTONIC_TEST_POSTGRES_URL=postgresql://postgres:postgres@localhost:5432/postgres pytest tests/contract -v
```
`tests/product-slices/` — see its own README for the exact setup; briefly:
```bash
cd tests/product-slices
uv venv && source .venv/bin/activate
uv pip install pytest pytest-asyncio httpx fastapi uvicorn \
  "opentelemetry-api>=1.27" "opentelemetry-sdk>=1.27" \
  "opentelemetry-instrumentation-fastapi>=0.48b0" "opentelemetry-instrumentation-httpx>=0.48b0"
pytest -v   # stands the whole stack up and tears it down itself
```

## 11. Environment and Running Locally

```bash
# Start local infra (no Docker in this sandbox — see CLAUDE.md).
# Check both are actually up before trusting a "connection refused" —
# neither reliably persists across a container restart in this sandbox.
sudo pg_ctlcluster 16 main start
redis-server --daemonize yes --port 6379 --save "" --appendonly no

# Per module
cd modules/<name>
uv venv && uv pip install -e ".[dev]"
source .venv/bin/activate
ruff check src tests
pytest tests/unit -v
TECTONIC_TEST_POSTGRES_URL=postgresql://postgres:postgres@localhost:5432/postgres pytest tests/integration -v   # if tests/integration/ exists
TECTONIC_TEST_POSTGRES_URL=postgresql://postgres:postgres@localhost:5432/postgres pytest tests/contract -v      # if tests/contract/ exists

# The whole support-agent product slice, live (see tests/product-slices/README.md)
python3 scripts/product-slice-stubs/stack.py          # up: launches all 15 modules + mock stub, seeds, posts the workflow definition
python3 scripts/product-slice-stubs/stack.py down     # tear down by port scan
```

Postgres local dev credentials: role `postgres`, password `postgres`,
`localhost:5432`. Platform-wide insecure JWT shared secret:
`dev-insecure-shared-secret-change-me` (every module's own zero-config
default). Neither is a production credential.

## 12. Backlog (P0/P1/P2/P3)

- **P0**: Two closed this session (see the "P0 -- DONE" entries below);
  several remain open from the reassessment's own Phase 1A backlog (IAM
  v2's own contract-test-tier rollout to the ~29 modules that don't have
  it, provisioning-saga reconciliation, universal operation-level
  authorization, a real external access gateway, event-backbone
  consumer/inbox pattern, image supply-chain build/scan/sign/admission
  gates, branch-protection required-status-check configuration -- no
  GitHub MCP tool found for that last one this session). Nothing is
  currently broken or blocking merge; all touched modules are green
  (including in real GitHub Actions CI, not just this sandbox -- see the
  note on `TECTONIC_TEST_POSTGRES_URL`-vs-CI-credentials below).
- **P1 -- DONE (this session).** The platform-wide NUL-byte-in-a-raw-
  `Query()`-string-parameter bug class (originally surfaced for real by
  the new CI job's own first run, against Multi-tenancy's and Billing
  and Metering's contract tiers) is now fixed everywhere it was found.
  Swept every module: a2a, agent-cards, agent-marketplace, auditability,
  deployment-strategy, finops, graph-db, human-oversight,
  identity-and-access (two route files), knowledge-base, llmops, mcp,
  multi-modality, observability, promptops, regulatory-compliance,
  sdk-and-developer-portal, secrets-and-credential-management,
  sentinel-agents -- each got a `_reject_null_byte_query()` helper
  applied to every affected route, a regression test, and a README
  note. The same pass also caught and fixed the sibling bug class (a
  route hand-converting a raw `str` into an Enum, raising an unhandled
  `ValueError`/500 instead of a clean 422) wherever it co-occurred:
  a2a, agent-marketplace, finops, identity-and-access,
  multi-modality, sdk-and-developer-portal, secrets-and-credential-
  management, observability, guardrails (guardrails' own instance was a
  body field, not a query param).

  Re-grepping the whole platform once the originally-scoped module list
  was done found six more modules with the *same* class of bug hiding
  in a different shape: a plain, un-wrapped `str` function parameter
  (no explicit `Query()` default) rather than the `Query(None)` pattern
  the first grep matched on -- `tenant_id: str,` with no default reads
  as a required query parameter to FastAPI just the same, but doesn't
  contain the literal substring `Query(`. Fixed: evaluation-framework
  (`tenant_id`/`agent_ref`), intent-detection (`tenant_id`),
  llm-gateway (`tenant_id`; re-running that module's own contract tier
  after the fix also surfaced a sibling *body*-field NUL-byte gap on
  `POST /admin/providers|virtual-keys|budget-policies`, fixed with the
  established `_reject_null_byte` `field_validator` pattern),
  long-term-memory (`agent_ref`), tool-orchestration (`status`). Left
  deliberately unfixed: Vector DB's `DELETE /points/{point_id}`'s
  `tenant_id` and `POST /query`'s `body.tenant_id` build a Qdrant alias
  string, not a Postgres query parameter -- this bug class is
  specifically "reaches asyncpg/Postgres unguarded", and Vector DB's
  `tenant_id` here never does, so it's out of this class's scope (a
  malformed Qdrant alias is a different, unverified failure mode this
  sandbox has no Qdrant to reproduce against).

  Every touched module was re-verified after its fix: `ruff check`
  clean, `pytest tests/unit` green, and `pytest tests/integration`
  (against this sandbox's real local Postgres) green wherever that tier
  exists; llm-gateway's `tests/contract` tier (schemathesis) was also
  re-run and now passes where it previously failed on the body-field
  gap. Pushed and confirmed green on a real GitHub Actions run (run
  `33303324479`/`33308091217`, commit `55628d3`); PR #9 opened
  (`claude/practical-wozniak-l1723c-rw7pp0` -> `claude/practical-wozniak-l1723c`).
- **P1 -- DONE (this session).** Phase 2's own first post-#82 vertical
  slice, per the independent architecture assessment now on file in full
  (§1-12; see `docs/` -- ask the user for it again if a future session
  can't find it, it isn't checked into the repo): **Conversational
  Engine completeness**. Three real gaps closed, all evidence-based
  (grepped/read the actual code, not inferred from filenames, per the
  assessment's own §10 master-prompt methodology): (1) session
  list/search/export/delete -- only `GET /{id}` existed before; (2)
  cross-session identity continuity actually wired -- `SessionManager`
  never received a `LongTermMemoryClient` port instance at all despite
  the LLD's own named differentiator and config flag for it, dead
  wiring, now fixed and called once per turn (best-effort, fail-open);
  (3) every one of this module's own peer HTTP clients' real wire
  shape -- standing this module's own DIRECT (non-`workflow_routing`)
  turn-handling path up against real peers for the first time (ticket
  #82's own product-slice test only ever exercised the
  `workflow_routing` path) surfaced that every client here except
  `HTTPWorkflowEngineClient`/`HTTPAuditabilityClient` was calling an
  invented endpoint -- including this module's own flagship streaming
  feature calling an LLM Gateway route that doesn't exist at all. Full
  account (every peer's real route/schema, and what's deliberately still
  open: per-tenant virtual key resolution, Long-Term Memory write-back,
  true upstream token streaming, voice/WebSocket channels, the broader
  Long-Term Memory "memory governance" gap) in that module's own
  README and root README's own Phase 2 section. Ruff clean, 85 unit +
  6 integration tests green (2 new integration tests, 1 new unit file
  for wire shapes, 1 new unit file for routes -- this module had NO
  route-level test file before this). **Merged**: this, plus ticket #82
  and the NUL-byte sweep above, all shipped in PR #9
  (`claude/practical-wozniak-l1723c-rw7pp0` -> `claude/practical-wozniak-l1723c`,
  merge commit `52a339d`, CI confirmed green on the merge commit). The
  designated branch was then reset to the new merged tip before starting
  the next item below, per this platform's "a merged PR's branch starts
  fresh from the current default branch" convention.
- **P0 -- DONE (this session).** Independent architecture assessment's
  own P0 Phase 1A closure item, user-selected: `EntitlementGateMiddleware`
  used to fail open *unconditionally and indefinitely* on any
  Multi-tenancy outage -- fixed with a bounded-staleness, HMAC-signed
  decision cache, as a reference implementation in **Agent Cards**
  (the platform's existing reference module for this middleware) and
  **Conversational Engine**. A verified decision is still served for up
  to `entitlement_gate_max_staleness_seconds` (default 300s) after
  Multi-tenancy becomes unreachable; past that window (or with no
  verified decision cached at all) the request now fails **closed**
  (`402`) instead of silently allowing. Two new Prometheus counters
  (`entitlement_gate_stale_served_total`, `entitlement_gate_fail_closed_total`)
  make both outcomes observable. Full design in
  `docs/entitlement-gate-rollout.md`'s new "Bounded-staleness cache
  upgrade" section, which also corrects that doc's stale "27 modules
  still need the base rollout" framing -- direct inspection confirmed
  all 28 selectable modules already carry the base (fail-open) version
  of this middleware; the base rollout itself is done, only this
  bounded-staleness upgrade is not yet ported everywhere. Explicitly
  NOT done in this pass: porting the upgrade to the other 26 modules
  (mechanical, tracked in that doc), and the same fail-open gap in
  `QuotaEnforcementService`'s consumers (LLM Gateway's
  `requests_per_minute` check, Vector DB's `vector_count` check) --
  related but distinct, a quota check rather than a binary gate, not
  touched here. Ruff clean, all unit tests green in both modules
  (conversational-engine 89, agent-cards 61), including 6 new tests per
  module covering the stale-serve window, the fail-closed boundary, a
  denied decision staying denied when served stale, and a forged cache
  signature being rejected.
- **P0 -- DONE (this session).** Independent architecture assessment's
  own P0 Phase 1A closure item, user-selected: "IAM v2 foundation". Two
  real, evidence-based gaps found by direct inspection of Identity and
  Access (not previously documented anywhere): `RoleRecord.name` was the
  sole, platform-global primary key -- a second tenant could never
  create a role with a name any other tenant already used, full stop
  (the `create_role` call just failed); and there was no way to grant or
  revoke a single role on an already-registered identity at all --
  `role_names` could only ever be set once, at `register()` time, no
  endpoint existed to change it after. Both fixed:
  - **Tenant-scoped roles**: `Role` gained `id`/`tenant_id`, PK moved
    from `name` to `id`, real unique constraint on `(tenant_id, name)`
    (Alembic `0003`, backfills every pre-existing role as
    `PLATFORM_TENANT_ID` -- a sentinel, not `None`, kept consistent with
    every other non-nullable `tenant_id` field in this module --
    preserving exactly the access every identity already had).
    `RoleService.get`/`TokenService.issue`/`IdentityRegistryService.
    register`'s role check all resolve tenant-then-platform-fallback; a
    tenant's own role shadows a platform default of the same name.
  - **Role bindings**: new `core/role_binding_service.py`,
    `POST /identities/{id}/roles` (grant) /
    `.../roles/{role_name}/revoke` (revoke) /
    `GET /identities/{id}/role-bindings` -- each grant/revoke writes/
    updates a durable `RoleBindingRecord` (`granted_by`/`granted_at`/
    `revoked_at`), one row per grant revoked in place, the same
    "materialized view + event log" split this module already uses for
    `AuthDecisionRecord`. Idempotent grant (no duplicate row for an
    already-held role); revoke of a never-granted role raises a clean
    404, not a silent no-op.
  - **Deliberately not built**: a separate `TenantMembership` entity --
    every `IdentityRecord` already belongs to exactly one tenant for its
    whole life, so `RoleBindingRecord` already *is* this module's
    membership record; cross-tenant identity membership (one identity,
    multiple tenants) isn't modeled at all, same posture as
    OIDC/SAML/SCIM JIT-provisioning already take. Also not touched: the
    other P0 Phase 1A items (IAM v2's own contract-test tier, the
    provisioning-saga/authorization/gateway/event-backbone/supply-chain
    items below).
  Full design in that module's own README's "Design notes vs. the LLD"
  section. Ruff clean; 169 unit tests green, including new
  `test_role_binding_service.py` and extended
  `test_role_service.py`/`test_routes_identity_and_access.py`
  coverage (tenant isolation, the 409-on-duplicate-name case, the
  platform-wide-fallback/shadowing case, grant/revoke/list-bindings
  end-to-end through real routes); 13 integration tests green against
  real Postgres including two brand-new role-binding/tenant-scoping
  tests and the real Alembic `0003` migration itself running end-to-end
  (backfill included). **Merged**: PR #11
  (`claude/practical-wozniak-l1723c-rw7pp0` -> `claude/practical-wozniak-l1723c`,
  merge commit `8a763df`) -- but not cleanly: PR #11's own CI run found a
  real regression this exact tenant-scoped-roles change caused in two
  seed scripts (`seed_support_agent_demo.py`/`seed_subscription_tiers.py`
  posted to `POST /roles` with no `X-Tenant-Id`, silently relying on the
  old platform-global role namespace); root-caused from the real CI job
  logs, fixed (`72b38a2`), and verified by actually re-running the full
  15-module product-slice stack locally in this sandbox before pushing --
  see that commit's own message for the full account. Not a fix left for
  a future session: this was caught and closed within the same PR before
  merge.
- **P0 -- DONE (this session, continued immediately after IAM v2
  merged).** Contract-test tier rolled out to Identity and Access
  (`tests/contract/`, ported from Multi-tenancy's own reference
  implementation, ticket #73/#80) -- the specific next P0 Phase 1A item
  this session's own §13 already flagged as most relevant ("including
  Identity and Access itself, which still has none"). Its very first
  run found three real, previously-invisible bugs (this module had
  never had a contract tier before, so none of these were ever
  exercised):
  - A NUL byte in a request body field (`POST /roles`'s own `name`,
    first found; then `POST /authorize`'s `required_scope`, found on
    the very next run once the first was fixed -- it's persisted into
    `AuthDecisionRecord`, the audit trail, on every call, allowed or
    denied) crashed with an unhandled 500 instead of a clean 422. Ticket
    #82's own platform-wide sweep never covered this module's body
    fields (only ever covered raw `Query()` params platform-wide, and
    this module had no contract tier to surface the body-field version
    until now). Fixed with the same `_reject_null_byte` field-validator
    pattern applied across every persisted string field in
    `schemas/identity_and_access.py`.
  - `RegisterIdentityRequest.type` / `RegisterIdentityProviderRequest.
    provider_type` were bare `str` fields hand-converted to
    `IdentityType`/`IdentityProviderType` at the route -- the identical
    sibling bug class already fixed for `IdentityStatus` on the
    query-param side (ticket #82), never caught on these two body
    fields. Now typed directly on the request schema.
  - `GET /identities/{id}`, `GET /identity-providers/{id}`, `GET
    /groups/{id}`, `POST /scim-tokens/{id}/revoke` all handed a
    syntactically-invalid UUID path param straight to `session.get()`,
    crashing with an unhandled `DataError` instead of a clean 404 --
    this platform's own recurring "non-UUID path/query-param" class
    (first found in Multi-tenancy/Billing and Metering), fixed with the
    identical `_is_valid_uuid`-repository-guard pattern.
  All three have regression tests (schema-level ones provable with the
  in-memory fake in `tests/unit/`; the UUID-format one is real-Postgres-
  only, in `tests/integration/`, since a dict lookup in the fake never
  crashes on a malformed key the way `asyncpg` does). No `ci.yml` change
  needed -- the contract job is opt-in by directory existence, already
  wired platform-wide. Ruff clean; 174 unit (+5), 14 integration (+1),
  1 contract test green (internally fuzzes every non-SCIM operation
  this module's real OpenAPI schema declares). Full account in that
  module's own README and root README's own P0 narrative.
- **P1**: Fix Agentic RAG's own Graph DB/Knowledge-Base-symbolic-lookup
  client wire shapes properly (currently sidestepped via
  `hybrid_retrieval_enabled=false` for this slice only) once Knowledge
  Base has a real symbolic-lookup endpoint to fix them against.
- **P2**: A demo front-end for the support-agent slice (explicitly named
  as separately-scoped follow-up in the design doc). Roll the reference
  patterns from earlier tickets (quota pre-flight, event outbox,
  contract-test tier) out beyond their current modules.
- **P3**: LLM Gateway `tokens_per_minute` quota accounting design.

## 13. Recommended Next Task

**Two assessment documents exist now, reviewing two different commits --
read this carefully before trusting either one's "current state" claims.**
(1) The original assessment (26 Aug 2026, commit `1c5639d`, scored 41/100)
defined the overall Phase 0-5 roadmap. (2) A reassessment (30 Aug 2026,
commit `f60c2ff`, scored 50/100) reviewed `f60c2ff` believing it to be
"current head" -- it was actually the branch's OLD fork point, predating
ticket #82, the NUL-byte sweep, and Conversational Engine completeness
entirely, all of which existed only on the then-open PR #9. PR #9 is now
merged (see §12), so the branch state the reassessment thought it was
reviewing now roughly matches reality again -- but its own §5/§6
module-by-module scores and "has not started"-type claims about
already-completed work should still be treated with that history in
mind, not re-litigated as if they were fresh.

Neither assessment document is checked into this repo (only summarized in
commit messages/READMEs) and neither was attached as a file — the user
pasted both directly into the conversation. If a future session needs
either one again and doesn't have it in context, ask the user to paste it
again rather than trying to reconstruct it from README prose.

**This session's own work**: closed three of the reassessment's P0
Phase 1A items in sequence — the `EntitlementGateMiddleware`
bounded-staleness cache; Identity and Access's IAM v2 foundation
(tenant-scoped roles + a real role-binding lifecycle), merged as PR #11
(with a real seed-script regression found by that PR's own CI and
fixed before merge — see §12's own account); and, immediately after,
Identity and Access's own contract-test tier (§12's newest "P0 -- DONE"
entry), which itself found and fixed three more real bugs (NUL-byte
body fields, two enum-hand-conversion body fields, four non-UUID
path-param lookups). Confirm current push/PR state with `git log`/
`git status` on `claude/practical-wozniak-l1723c-rw7pp0` and a live
check of open PRs before assuming any of this is or isn't merged yet —
this file is a point-in-time snapshot, not a live source of truth for
that; the contract-tier work in particular may still be uncommitted/
un-PR'd depending on exactly when this snapshot was taken relative to
that work finishing.

**Remaining P0 Phase 1A closure items from the reassessment's own
backlog, not yet started**:

- Contract-test tier rolled out further — Identity and Access is now
  done (this session); ~28 modules still don't have it. Multi-tenancy's
  own `tests/contract/conftest.py` remains the reference implementation
  to copy (the two established harness fixes: swap the real `lifespan`
  for a no-op before schemathesis drives the ASGI app, and use a
  `NullPool`-backed engine for the contract-test app context).
- Provisioning-saga/resource-allocation reconciliation.
- Universal operation-level authorization; a real external access
  gateway; event-backbone consumer/inbox pattern; image supply-chain
  build/scan/sign/admission gates; branch-protection required-status-
  check configuration (no GitHub MCP tool found for this in this
  session — likely needs manual repo-settings configuration or a
  different tool).

**Also queued, from the entitlement-gate work itself** (see
`docs/entitlement-gate-rollout.md`): port the bounded-staleness upgrade
from Agent Cards/Conversational Engine to the other 26 modules
(mechanical); apply the same bounded-staleness pattern to
`QuotaEnforcementService`'s fail-open consumers (LLM Gateway, Vector DB)
— a related but distinct gap, a quota check rather than a binary gate.

**Still-open Phase 2 candidates from the earlier assessment, not picked
yet**: memory governance (Long-Term Memory's consent/purpose/legal-hold
gap, currently zero coverage), the evaluation-gated release path (wiring
Evaluation Framework's own `/gate` as an actual blocking check before
PromptOps publish / LLMOps canary promotion), PromptOps' own full
review/approve/publish lifecycle. Ask the user which comes next rather
than assuming — this session's pattern has been to offer options via
`AskUserQuestion` and let the user pick.

## 14. Important Context for Next Claude Session

- Read `CLAUDE.md` first (durable conventions), then this file, then the
  relevant module READMEs before writing any code.
- The root `README.md` is the authoritative narrative of every design
  decision made so far, organized chronologically by ticket — grep it for
  a ticket number or module name rather than re-deriving "why" from
  source.
- **Before running any single module's own `tests/integration`/
  `tests/contract` tier, confirm no `stack.py`-launched live process is
  still running** (`ps aux | grep uvicorn`) — see §8's own documented
  false-regression class this exact mistake caused mid-session.
- No Docker daemon in this sandbox is a recurring, real constraint — it
  shaped both ticket #80's contract-test harness fixes and ticket #82's
  entire live-verification approach (real per-module Postgres processes
  instead of docker-compose). Don't assume it will "probably work" without
  checking.
- Ticket #82 is fully done, committed, and pushed
  (`claude/practical-wozniak-l1723c-rw7pp0`, commit `4d7197c`) — do not
  redo or second-guess it without new evidence; build on top of it.

## 15. Resume Prompt

Paste the following into a new Claude Code session to resume:

```
Continue work on the Tectonic Agentic AI Platform repository. Before doing
anything else, read CLAUDE.md (durable, every-session conventions) and
SESSION_HANDOFF.md (this session's handover snapshot) at the repo root in
full.

Ticket #82 (the Phase 2 support-agent product slice, built and verified
end-to-end against real running module instances) is done, committed, and
pushed to claude/practical-wozniak-l1723c-rw7pp0. Pick up the next task from
SESSION_HANDOFF.md §12's backlog, or ask what Phase 2 slice #2 should be —
whichever the user actually wants; don't assume.

Before running any single module's own tests/integration or tests/contract
tier, confirm no live product-slice stack process is still running
(`ps aux | grep uvicorn`) — a leftover live stack from a manual
scripts/product-slice-stubs/stack.py run gives an unrelated module's own
contract test a real peer instead of the no-op/stub it expects, which reads
as a false regression (see SESSION_HANDOFF.md §8 for the full diagnosis).

Follow this repo's established conventions: real infrastructure in tests
(real local Postgres via TECTONIC_TEST_POSTGRES_URL, real HTTP calls
between modules, no mocking of this platform's own peer modules), update
both the touched module(s)' own README and the root README's running
narrative with what was built and what deliberately remains out of scope,
and keep every module's full test suite (ruff + unit + integration +
contract, per module) green throughout.
```
