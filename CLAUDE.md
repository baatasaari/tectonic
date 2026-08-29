# Repository-level instructions for Claude Code

Durable conventions that apply to **every** session working in this repo, not
just the one that wrote this file. Point-in-time state (what was done last
session, what's next) lives in `SESSION_HANDOFF.md`, not here — update that
file per-session; update this one only when a convention itself changes.

## What this repo is

Tectonic is a 34-module "Agentic AI Platform." Each module under `modules/`
is an independently deployable FastAPI service (async SQLAlchemy + Postgres,
its own `pyproject.toml`/`.venv`/tests/README/Helm chart). Start with the
root `README.md` (long — grep it) and `docs/agentic-platform-final-module-table.md`
for the overall shape; each module's own `README.md` documents that module's
design decisions and its own "not built yet" list in detail — don't
re-derive that from source, read it.

## Sandbox infrastructure (every session, not just this one)

- **No Docker daemon is available in this sandbox.** `docker`/`docker compose`
  commands fail (`no such file or directory` on the socket). Do not spend
  time debugging this as if it were transient — plan around it:
  - **Postgres**: a local Postgres 16 cluster is installed. Start it with
    `sudo pg_ctlcluster 16 main start`. The `postgres` role's password is
    `postgres` (persists across container restarts on the same data dir).
    Use it for real `tests/integration`/`tests/contract` runs via
    `TECTONIC_TEST_POSTGRES_URL=postgresql://postgres:postgres@localhost:5432/postgres`
    instead of testcontainers/Docker-backed Postgres.
  - **Redis**: `redis-server --daemonize yes --port 6379 --save "" --appendonly no`.
  - **Kafka**: no local broker and no Docker — anything needing a *real*
    Kafka (e.g. exercising `OutboxRelayWorker` end-to-end against a live
    broker, or module docker-compose stacks with a Kafka service) cannot be
    verified in this sandbox today. Say so rather than silently skipping or
    faking it; this is a real open constraint, not a solved one.
- CI (`.github/workflows/ci.yml`) always starts a real Postgres service
  container and runs `tests/integration`/`tests/contract` for any module that
  has those directories (opt-in by directory existence — adding a tier to a
  module needs no workflow change).

## Per-module workflow

```bash
cd modules/<module-name>
uv venv && uv pip install -e ".[dev]"
source .venv/bin/activate
ruff check src tests
pytest tests/unit -v
# only if the directory exists for that module:
TECTONIC_TEST_POSTGRES_URL=postgresql://postgres:postgres@localhost:5432/postgres pytest tests/integration -v
TECTONIC_TEST_POSTGRES_URL=postgresql://postgres:postgres@localhost:5432/postgres pytest tests/contract -v
```

A module is "green" only when `ruff check` is clean **and** every tier it has
passes for real (integration/contract tiers must actually run against real
Postgres, not be skipped for lack of `TECTONIC_TEST_POSTGRES_URL`).

## Testing discipline established in this project

- **Real infrastructure, real peers.** Tests against this platform's own
  peer modules use real HTTP clients against real (or realistically faked)
  peers, not mocks of this platform's own code. Integration/contract tiers
  run against a real Postgres, never SQLite-as-a-stand-in.
- **schemathesis/Hypothesis contract tests** (`tests/contract/`, OpenAPI-
  schema-driven fuzzing against a live ASGI app + real Postgres): every
  module adopting this tier hits the same two harness issues, already
  solved — copy the fix from an existing `tests/contract/conftest.py`
  (e.g. `modules/multi-tenancy/tests/contract/conftest.py`) rather than
  rediscovering it:
  1. schemathesis's ASGI transport actually drives the ASGI lifespan
     protocol, so a module whose real `lifespan()` has side effects (Kafka
     producer, outbox worker, outbound HTTP clients) needs it swapped for a
     no-op before use.
  2. schemathesis's synchronous `case.call()` bridges into the app through a
     fresh event loop per call — reusing the app's normal pooled
     `AsyncEngine` leaks a connection every call and exhausts
     `max_connections` within one run. Use a `NullPool`-backed `AsyncEngine`
     for the contract-test app context instead, and rebuild every dependent
     repository/service that had already captured the old pooled session
     factory at construction time.
- When you fix a bug found by fuzzing/contract tests, look for the same bug
  class across sibling endpoints/modules before calling it done (this
  project's own history: the unbounded-`offset` class and the non-UUID
  path/query-param class each recurred across multiple modules once looked
  for).

## Conventions

- Work on a `claude/<slug>` branch; CI (`.github/workflows/ci.yml`) triggers
  on `push`/`pull_request` to `claude/**`.
- Every module fix/feature: update that module's own `README.md` **and** the
  root `README.md`'s running narrative — this repo's established style is to
  explicitly document what a change does *and* does not do yet, in prose, so
  the next session/reader doesn't have to re-derive scope from the diff.
- Don't invent scope. When a gap is out of scope for the current fix, say so
  explicitly (in code comments/docstrings and in the README narrative)
  instead of silently leaving it undocumented.
- End commits with the standard Claude Code attribution footer (session URL
  is session-specific — include whatever footer your own harness normally
  appends; don't hardcode a prior session's URL into new commits).
