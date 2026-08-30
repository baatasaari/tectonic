# Product-slice tests

Ticket #82's own net-new automated test tier: real, end-to-end integration
tests that stand up an entire live product slice (currently just the one,
[Phase 2 support-agent slice](../../docs/phase2-product-slice-01-support-agent.md))
across many real module processes at once, rather than one module in
isolation. Every other test tier in this repo (`tests/unit`,
`tests/integration`, `tests/contract` inside each `modules/<name>/`) tests
exactly one module against its own real dependencies-or-fakes; this
directory is the deliberate, narrow exception, not a new house style —
proving that several modules actually *compose* correctly needs more than
one module answering.

## What's here

- `conftest.py` — the `live_stack` session-scoped fixture. It imports
  `scripts/product-slice-stubs/stack.py` and calls its `up_all()`: launches
  all 15 modules in this slice's own critical path plus one small mock
  stub (an LLM provider and a merchant's order-status backend — the only
  two things genuinely outside this platform's own 34 modules) as real
  `uvicorn` processes against real per-module Postgres databases (no
  Docker — this sandbox has none, see the repo root `CLAUDE.md`'s own
  "Sandbox infrastructure" section), seeds a real Acme Corp tenant end to
  end, and posts the slice's own real workflow definition. Torn down at
  the end of the test session (or immediately, if setup itself fails) —
  every module's own `tests/contract/` tier depends on nothing else being
  live on its peers' real ports, so a stack left running here would give
  an unrelated module's contract test a real peer instead of the
  no-op/stub it expects (this is exactly how a real regression during
  this ticket's own development was diagnosed: multi-tenancy's contract
  test failed only because a previous manual run of this stack was still
  running underneath it).
- `test_support_agent.py` — the three scripted conversations the design
  doc's own "Definition of done" names, plus the Auditability/Billing/
  Human-Oversight-resolution checks that same section calls for.
- `test_trace_propagation.py` — a standalone, platform-wide regression
  test (doesn't use `live_stack` at all) for the cross-process W3C
  `traceparent` propagation fix Observability's own README already
  documents but never had a committed automated test for. See that file's
  own docstring for why it's scoped to proving trace_id continuity across
  one real HTTP hop, not spans actually landing in Observability's real
  store (no real OTel Collector/Tempo is available in this sandbox
  either — a documented, unclosed gap, not a silently skipped one).

## Running it

This directory is its own small, flat Python project (`pyproject.toml`),
not a `modules/<name>/`-shaped module — it has no `src/` package of its
own to import, just test files and a couple of light runtime dependencies
(`httpx`, `fastapi`, `opentelemetry-*`, `pytest`/`pytest-asyncio`).

```bash
cd tests/product-slices
uv venv
source .venv/bin/activate
uv pip install pytest pytest-asyncio httpx "opentelemetry-api>=1.27" \
  "opentelemetry-sdk>=1.27" "opentelemetry-instrumentation-fastapi>=0.48b0" \
  "opentelemetry-instrumentation-httpx>=0.48b0" "fastapi>=0.115" "uvicorn>=0.32"
```

Prerequisites, same as every other module's own `tests/integration`/
`tests/contract` tier per the repo root `CLAUDE.md`: a local Postgres 16
cluster running (`sudo pg_ctlcluster 16 main start`) and Redis
(`redis-server --daemonize yes --port 6379 --save "" --appendonly no`).
Every module in the slice needs its own `.venv` already built (`cd
modules/<name> && uv venv && uv pip install -e ".[dev]"`) — this fixture
launches each module's real `uvicorn` server from that venv directly, it
doesn't build them.

```bash
pytest -v
```

Runs in well under two minutes locally: the fixture brings the whole stack
up, seeds it, runs every test, and tears it back down again, all in one
session.

## In CI

`.github/workflows/ci.yml`'s own `product-slice-support-agent` job runs
this exact tier on every push/PR to `claude/**`, same as every module's
own unit/integration/contract tiers — it's a required check
(`needs` on the aggregate `ci` job), not an optional/best-effort one. It's
its own job rather than folded into the per-module `lint-and-test` matrix:
this tier needs all 15 of this slice's own modules running as real
processes simultaneously, not one module tested in isolation, so it
doesn't fit that job's per-module shape. The job builds each of the 15
modules' own `.venv`s (same as running any one of them locally — no
shared/system install, matching this platform's own per-module dependency
isolation), starts real `postgres:16-alpine` and `redis:7-alpine` service
containers, then runs this exact `pytest -v`. `scripts/product-slice-stubs/
stack.py`'s own Postgres connection is env-overridable
(`TECTONIC_STACK_POSTGRES_{HOST,PORT,USER,PASSWORD}`) specifically for
this — CI's service container uses different credentials
(`tectonic_ci`/`tectonic_ci`) than this sandbox's own local dev Postgres
(`postgres`/`postgres`), and `stack.py`'s own `ensure_databases()`
creates each module's own database on a fresh service container that
starts with none of them yet (idempotent, so it's also a safe no-op
against this sandbox's own already-provisioned local cluster). On
failure, every module's own real log file
(`scripts/product-slice-stubs/stack.py`'s own per-process log, exactly
what a local run leaves in `/tmp/support-agent-slice-logs/`) is uploaded
as a workflow artifact — that's the fastest way to see which real module
actually failed, faster than re-running locally from scratch.

## What this deliberately does not cover

Same scope boundaries the design doc itself draws: no second tenant/
cross-tenant isolation proof (Multi-tenancy's own isolation probe already
covers this platform-wide), no UI, no load/scale testing. See the design
doc's own "What this slice deliberately does not cover" section for the
full reasoning.
