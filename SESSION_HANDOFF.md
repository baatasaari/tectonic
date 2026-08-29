# Session Handoff

Prepared 2026-08-29 for a clean handover to a new Claude Code session. This
file is a point-in-time snapshot; durable, every-session conventions live in
`CLAUDE.md` instead — read that first, then this.

## 1. Project Objective

Tectonic is a 34-module "Agentic AI Platform" being built module-by-module
against low-level design specs in `docs/module-NN-*.md`, tracked against
`docs/agentic-platform-final-module-table.md`. Work proceeds in tickets: a
"Phase 1 kernel" pass closed cross-cutting platform gaps (auth, entitlements,
observability, supply chain, etc. — see `git log --oneline` for the full
list, each commit subject is a ticket). The current phase ("Phase 2") is
building real product slices on top of the now-complete kernel; the first
slice is a tenant support agent, designed in
`docs/phase2-product-slice-01-support-agent.md`.

## 2. Current Architecture

Each module under `modules/<name>/` is an independently deployable FastAPI
service: async SQLAlchemy + its own Postgres schema (Alembic migrations),
`ServiceAuthMiddleware` (service-to-service JWT) + `EntitlementGateMiddleware`
on every non-Platform-Base module, OpenTelemetry tracing, Prometheus
`/metrics`, its own Helm chart under `deploy/helm/`. Modules call each other
over real HTTP with resilient clients (`ResilientHTTPClient` — circuit
breaker via `aiobreaker`), never in-process imports of a peer's code. Two
cross-cutting patterns introduced this session, now used by more than one
module:
- **CloudEvents + transactional outbox** event backbone (`core/events.py`,
  `event_outbox` table, `OutboxRelayWorker` claim/lease/poison-pill via
  `SELECT ... FOR UPDATE SKIP LOCKED`, relayed to Kafka via
  `KafkaEventPublisher`) — Workflow Engine (pre-existing) and now
  Multi-tenancy's Tenant lifecycle only.
- **Quota pre-flight enforcement** — real modules calling Multi-tenancy's
  `POST /tenants/{id}/quota/check` before doing work, via
  `HTTPMultiTenancyClient` (fails open on any Multi-tenancy-side error).
  Two shapes: rate-shaped (Multi-tenancy owns the counter — LLM Gateway,
  `requests_per_minute`) and capacity-shaped (caller supplies
  `current_usage` — Vector DB, `vector_count`).

Full architectural detail is in each module's own README and LLD doc — this
section is deliberately not a re-derivation of those.

## 3. Repository Structure

```
docs/            Low-level design specs (module-01..34), module table,
                 entitlement-gate rollout notes, Phase 2 slice design
modules/<name>/  34 independently-deployable services (src/, tests/, deploy/,
                 pyproject.toml, README.md — see CLAUDE.md for the workflow)
scripts/         generate_openapi_specs.sh, seed_subscription_tiers.py
test-data/       subscription-tiers/ fixture JSON used by seeding scripts
.github/workflows/ci.yml   Per-module lint+test matrix, SBOM+sign, gate job
README.md        Long running narrative of every ticket's design decisions —
                 the primary source of truth for "why", not this file
CLAUDE.md        Durable, every-session instructions (NEW this session)
SESSION_HANDOFF.md   This file (NEW this session)
```

No `.claude/` directory exists in this repo.

## 4. Work Completed

This session closed four tickets (all committed and pushed to
`claude/practical-wozniak-l1723c`, working tree clean):

- **#78** (`86a4a0e`) — Wired LLM Gateway (rate-shaped) and Vector DB
  (capacity-shaped) to call Multi-tenancy's real `quota/check` before doing
  work, via a new `HTTPMultiTenancyClient` in each, fail-open posture.
- **#79** (`561faf8`) — Rolled Workflow Engine's CloudEvents+outbox pattern
  out to Multi-tenancy's Tenant lifecycle (`register`/`suspend`/
  `reactivate`/`delete`); new `event_outbox` table (migration `0006`), new
  `OutboxRelayWorker`/`KafkaEventPublisher`. Organisation/Workspace/
  Environment deliberately stay on the pre-existing best-effort Auditability
  path only.
- **#80** (`6bb7e7a`) — Rolled Billing and Metering's schemathesis/Hypothesis
  OpenAPI contract-test tier out to Workflow Engine, Multi-tenancy, Vector
  DB, LLM Gateway. Fixed two reusable harness issues (ASGI lifespan side
  effects, `NullPool` for the fuzzing event-loop-per-call pattern — see
  `CLAUDE.md`) and a real bug in every module fuzzing turned up (non-UUID
  path/query segments reaching `asyncpg` unguarded, unbounded `offset`,
  NUL bytes in free-text fields, invalid enum filters, degenerate vectors in
  Vector DB, etc. — full list in README.md's ticket #80 narrative).
- **#81** (`6bbfc03`) — Design doc for Phase 2's first product slice:
  `docs/phase2-product-slice-01-support-agent.md` (a tenant support agent —
  multi-turn dialogue, retrieval-grounded answers, a real tool call, human
  escalation, and the identity/entitlement/billing/audit/tracing path every
  one of those needs in production).

Each ticket's full reasoning/tradeoffs are narrated in the root `README.md`
(search for the ticket's fix description) and in the touched modules' own
READMEs — not duplicated here.

## 5. Files Changed

All already committed and pushed; see `git log --oneline` (commits
`86a4a0e`, `561faf8`, `6bb7e7a`, `6bbfc03`) and `git show --stat <sha>` for
exact diffs per ticket. Touched: `modules/{llm-gateway,vector-db}` (core
domain/ports/service/app_context/main/routes, new `clients/
multi_tenancy_client.py`, tests, README) for #78; `modules/multi-tenancy`
(events/outbox/kafka-publisher, db models+repository, config, app_context,
main, new Alembic migration `0006`, deploy manifests, tests, README) for
#79; four modules' `tests/contract/{conftest.py,test_openapi_contract.py}`
plus assorted repository/route/schema bug fixes for #80; `docs/
phase2-product-slice-01-support-agent.md` (new) for #81; root `README.md`
updated after every ticket. **New this handover session**: `CLAUDE.md`,
`SESSION_HANDOFF.md` (both at repo root).

## 6. Current Application State

`git status`: clean, branch `claude/practical-wozniak-l1723c`, up to date
with `origin/claude/practical-wozniak-l1723c` (before this handover's own
commit). All 4 modules touched this session re-verified green just now (see
§10). A broader spot-check of two untouched modules (billing-and-metering,
identity-and-access) also passed. No local Docker; local Postgres 16 and
Redis running (started this session, see `CLAUDE.md`).

## 7. Incomplete Work

- **Ticket #82 was paused before this handover, not started.** It is the
  next real product-slice ticket: build and verify the support-agent slice
  (`docs/phase2-product-slice-01-support-agent.md`) end-to-end against real
  running module instances. Blocked on a real infrastructure decision — see
  §9 and §13.
- Organisation → Tenant cascading offboarding (Multi-tenancy) remains
  unbuilt — `OrganisationService.delete`'s own docstring still flags it.
- LLM Gateway's `tokens_per_minute` quota class is deliberately not wired to
  quota/check (actual token count is only known after the provider
  responds — different accounting design, out of scope for #78's reference
  pass).
- Rolling the quota pre-flight pattern (#78), the event-outbox pattern
  (#79), and the contract-test tier (#80) out to the platform's remaining
  ~29 modules is explicitly named follow-up work in each ticket's README
  narrative, not started.

## 8. Known Issues

- No Docker daemon in this sandbox (confirmed again this session) — blocks
  anything needing a real Kafka broker or a module's own
  `docker-compose.yml` stack. See `CLAUDE.md` and §9.
- Deprecation warnings (non-blocking, pre-existing): `aiobreaker`'s internal
  use of `datetime.utcnow()`, and an Alembic `path_separator` config
  warning — both cosmetic, appear in every module's test output, not
  introduced this session.
- No known regressions or newly-introduced bugs from this session's four
  tickets — full suites re-run clean this handover (§10).

## 9. Decisions and Constraints

- **No secrets in this repo.** This file intentionally names only env var
  names (`TECTONIC_TEST_POSTGRES_URL`), never values beyond the sandbox's
  own well-known local dev password (`postgres`/`postgres` on
  `localhost:5432`, not a production credential).
- **Real infrastructure over mocks**, established and reinforced all
  session: integration/contract tests run against a real local Postgres
  (no Docker/testcontainers available here — see `CLAUDE.md`), modules call
  real peer HTTP APIs in tests, not mocks of this platform's own code.
- **Open decision point for #82**: the support-agent slice's end-to-end
  verification plan (per its design doc) implies exercising several modules
  together with real inter-service calls. Whether that needs a real Kafka
  broker (blocked — no Docker here) or can be verified with the modules'
  existing HTTP-only real-peer pattern (no Kafka involved in the slice's
  synchronous request path) needs to be re-checked against the design doc
  by the next session before deciding how to proceed — this was the open
  question pending when the handover request arrived.

## 10. Tests and Validation

Re-run for real this handover session (not assumed from memory), all green:

| Module | ruff | unit | integration | contract |
|---|---|---|---|---|
| workflow-engine | clean | 67 passed | 6 passed | 1 passed |
| multi-tenancy | clean | 173 passed | 19 passed | 1 passed |
| vector-db | clean | 61 passed | 3 passed | 1 passed |
| llm-gateway | clean | 74 passed | 3 passed | 1 passed |

Commands used (per module, from `modules/<name>/`):
```bash
source .venv/bin/activate   # after uv venv && uv pip install -e ".[dev]"
ruff check src tests
pytest tests/unit -v
TECTONIC_TEST_POSTGRES_URL=postgresql://postgres:postgres@localhost:5432/postgres pytest tests/integration -v
TECTONIC_TEST_POSTGRES_URL=postgresql://postgres:postgres@localhost:5432/postgres pytest tests/contract -v
```
No build step beyond `uv pip install -e ".[dev]"` (no compiled artifacts;
pure Python services). CI (`.github/workflows/ci.yml`) runs the same
commands per-module in a matrix, plus SBOM generation/signing on push.

## 11. Environment and Running Locally

(No secrets or credentials below beyond the sandbox's own well-known local
dev Postgres password.)

```bash
# Start local infra (no Docker in this sandbox — see CLAUDE.md)
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

# Full local stack for one module (requires Docker — unavailable in this sandbox)
docker compose -f deploy/docker-compose.yml up --build
```

Postgres local dev credentials: role `postgres`, password `postgres`,
`localhost:5432` — this is the sandbox's own pre-provisioned local cluster,
not a shared or production credential.

## 12. Backlog (P0/P1/P2/P3)

- **P0**: None. Nothing is broken or blocking; all touched modules are
  green.
- **P1**: Ticket #82 — build and verify the Phase 2 support-agent product
  slice end-to-end (see §13). This is the natural next task.
- **P2**: Roll the three new reference patterns (quota pre-flight, event
  outbox, contract-test tier) out beyond their current reference-implementation
  modules to the rest of the platform, per each ticket's own README
  follow-up note. Organisation → Tenant cascading offboarding in
  Multi-tenancy.
- **P3**: LLM Gateway `tokens_per_minute` quota accounting design (needs a
  genuinely different post-hoc accounting shape, not a mechanical rollout).

## 13. Recommended Next Task

**Ticket #82 — Build and verify the Phase 2 support-agent product slice.**

- **Objective**: Stand up and verify, end-to-end against real running
  module instances (not just unit tests), the tenant support-agent scenario
  designed in `docs/phase2-product-slice-01-support-agent.md`: multi-turn
  dialogue, retrieval-grounded answers, a real tool call, a genuine
  human-escalation path, and the identity/entitlement/billing/audit/tracing
  governance path each of those needs in production.
- **Relevant files**: `docs/phase2-product-slice-01-support-agent.md` (the
  design — read this first, in full); the modules it names as slice
  participants (re-read the doc to get the exact list — likely includes
  Conversational Engine, LLM Gateway, Agentic RAG / Knowledge Base / Vector
  DB, Tool Orchestration, Human Oversight, Identity and Access,
  Multi-tenancy, Billing and Metering, Auditability, Observability).
- **Dependencies / open question to resolve first**: whether the slice's
  verification plan requires a real Kafka broker (blocked in this sandbox —
  no Docker daemon; see `CLAUDE.md` §"Sandbox infrastructure") or can be
  fully verified through the modules' existing real-HTTP-peer pattern with
  no Kafka in the synchronous path. Re-check this against the design doc's
  own verification section before starting build work; if Kafka turns out
  to be required, that's a decision point for the user (accept
  unverified-against-real-Kafka status, find/install a non-Docker Kafka
  option, or scope verification down) rather than something to silently
  route around.
- **Acceptance criteria**: each module participating in the slice is called
  for real (real HTTP, real Postgres) in at least one end-to-end test path
  that walks the scenario from a user's opening message through retrieval,
  tool call, and (for the escalation branch) a human-oversight handoff, with
  real entitlement/quota/audit/billing/tracing side effects verified, not
  asserted from mocks.
- **Tests required**: new end-to-end test(s) exercising the real
  multi-module flow (naming/location TBD by the next session — this
  platform doesn't yet have a "cross-module e2e" test tier convention;
  establishing one, or reusing an existing module's `tests/integration`
  convention across module boundaries, is part of this ticket's own design
  work). Every participating module's own existing unit/integration/contract
  tiers must stay green throughout.
- **Definition of done**: the slice runs and is verified per the design
  doc's own acceptance bar; root `README.md` updated with the ticket's
  narrative (per this repo's established convention — see `CLAUDE.md`);
  any newly-discovered "not built yet" gaps documented explicitly rather
  than silently left implicit; all module test suites green; branch pushed.

## 14. Important Context for Next Claude Session

- Read `CLAUDE.md` first (durable conventions), then this file, then the
  relevant module READMEs and `docs/phase2-product-slice-01-support-agent.md`
  before writing any code.
- The root `README.md` is the authoritative narrative of every design
  decision made so far, organized chronologically by ticket — grep it for a
  ticket number or module name rather than re-deriving "why" from source.
- No Docker daemon in this sandbox is a recurring, real constraint, not a
  one-off — it shaped ticket #80's contract-test harness fixes and is the
  open blocker for #82. Don't assume it will "probably work" without
  checking.
- This session's own four tickets (#78-81) are fully done, committed, and
  pushed — do not redo or second-guess them without new evidence; build on
  top of them.

## 15. Resume Prompt

Paste the following into a new Claude Code session to resume:

```
Continue work on the Tectonic Agentic AI Platform repository. Before doing
anything else, read CLAUDE.md (durable, every-session conventions) and
SESSION_HANDOFF.md (this session's handover snapshot) at the repo root in
full.

Then start on ticket #82, the "Recommended Next Task" in
SESSION_HANDOFF.md §13: build and verify the Phase 2 support-agent product
slice (docs/phase2-product-slice-01-support-agent.md) end-to-end against
real running module instances. Read that design doc in full first. Before
writing code, re-check whether the slice's verification plan requires a
real Kafka broker — this sandbox has no Docker daemon (see CLAUDE.md), so
if Kafka turns out to be required, stop and ask how to proceed rather than
silently working around it or faking it.

Work on branch claude/practical-wozniak-l1723c (already up to date with
origin). Follow this repo's established conventions: real infrastructure in
tests (real local Postgres via TECTONIC_TEST_POSTGRES_URL, real HTTP calls
between modules, no mocking of this platform's own peer modules), update
both the touched module(s)' own README and the root README's running
narrative with what was built and what deliberately remains out of scope,
and keep every module's full test suite (ruff + unit + integration +
contract, per module) green throughout.
```
