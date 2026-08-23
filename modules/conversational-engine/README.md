# Conversational Engine — Module 2

Owns the dialogue layer: turn management, streaming response delivery,
persona/tone enforcement, channel adaptation, and the decision of when to
hand off to a human or another agent. Delegates generation to LLM Gateway,
moderation to Guardrails, escalation to Human Oversight — this module
orchestrates those calls within a conversation, it does not duplicate their
logic. Full design doc: [`../../docs/module-02-conversational-engine.md`](../../docs/module-02-conversational-engine.md).

## Layout

Mirrors Module 1's package shape:

```
src/conversational_engine/
  main.py                 FastAPI app, lifespan wiring, /healthz, /metrics
  app_context.py           Process-wide dependency container
  config.py                 Pydantic Settings — LLD config schema
  core/
    domain.py                Session/Message/HandoffEvent/PersonaConfig dataclasses
    ports.py                  Repository, hot state store, and the module's 4 external clients
    fakes.py                   In-memory implementations of every port, for unit tests
    emotion.py                  Emotion/Urgency Detector — heuristic scorer with optional LLM refinement
    persona.py                   Persona Engine — prompt building + denied-topic short-circuit
    refusal.py                    Explainable Refusal Composer
    handoff.py                     Handoff Trigger Engine — deterministic escalation rules
    session_manager.py              The turn orchestrator (this module's "scheduler")
  db/                      SQLAlchemy 2.0 async models + repository (durable history)
  clients/                 Redis hot-state store, HTTP clients for the 4 external modules
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI routers — sessions, turn (SSE or JSON), handoff, close
  schemas/                    Pydantic request/response models
```

## Design notes vs. the LLD

- **Streaming.** `SessionManager.handle_turn` takes an optional `on_chunk`
  callback so the same turn-processing path serves both the SSE endpoint
  (`POST /sessions/{id}/messages?stream=true`) and a plain JSON response —
  no duplicated orchestration logic between the two.
- **Emotion/Urgency Detector.** The LLD calls for "a lightweight classifier
  ... not a separate heavyweight service." `core/emotion.py` implements a
  zero-latency heuristic scorer (frustration/urgency keyword markers,
  punctuation intensity, caps ratio) and only calls out to LLM Gateway's
  classification endpoint when that heuristic lands in an uncertain middle
  band — refinement, not a hard dependency on every turn.
- **Explainable refusal.** Both the Persona Engine's denied-topic check and
  a Guardrails block route through the same `RefusalComposer`, so every
  refusal — pre- or post-generation — carries a `violation_category`
  traceable to a specific rule.
- **Session state tiers.** Redis (`SessionStateStore`) holds only the
  per-session turn counters the Handoff Trigger Engine needs (e.g.
  consecutive refusals); Postgres holds the durable session/message/handoff
  history. Losing Redis loses escalation memory, not conversation history.
- **Postgres integration tests** — the repository layer is now also tested
  against a real Postgres (`tests/integration/`, opt-in via
  `TECTONIC_TEST_POSTGRES_URL` or Docker+testcontainers), covering nested
  `guardrail_check_result` / `tone_settings` / topic-list JSONB
  round-tripping and real UUID primary keys that SQLite's unit-tier fakes
  can't reliably prove. See `tests/integration/conftest.py` for how the
  Postgres instance is obtained.

## Running locally

```bash
uv venv && uv pip install -e ".[dev]"
pytest                                                    # unit tests, no external services needed

docker compose -f deploy/docker-compose.yml up --build    # full stack incl. Postgres, Redis, dependency-stub
```
