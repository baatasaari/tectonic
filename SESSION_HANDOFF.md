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

- **P0**: None. Nothing is broken or blocking; all touched modules are
  green.
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

No single next ticket is mandated by this session — ticket #82 (the prior
handoff's own "Recommended Next Task") is done. Pick from §12's backlog, or
ask the user what Phase 2 product slice comes next (the design doc's own
module-role table names SDK/Developer Portal and a second, differently-shaped
scenario as natural candidates for a slice #2, per root README's "What this
slice deliberately does not cover" section).

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
