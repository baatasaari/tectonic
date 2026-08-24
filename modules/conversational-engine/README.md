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

- **Connection pooling tuned to replica count.** SQLAlchemy's out-of-
  the-box defaults (`pool_size=5`, `max_overflow=10`) are the same
  regardless of how many pods are running — at this module's own
  `deploy/helm/conversational-engine/values.yaml` `autoscaling.maxReplicas: 20`,
  that's up to 300 connections to this module's own Postgres
  instance from this module alone at full autoscale, with no one having
  deliberately decided that number. `db/session.py`'s `make_engine` now
  passes explicit, configurable `pool_size=5` /
  `max_overflow=2` (`db_pool_size`/`db_max_overflow`
  Settings, env-overridable) sized so this module's own steady-state
  total stays at ~100 connections and its full-burst total at ~150,
  even at `maxReplicas`. `pool_recycle=1800s` also avoids stale
  connections behind a cloud LB/proxy's own idle-connection timeout —
  a real, independent gap, not just a replica-count one.

## Running locally

```bash
uv venv && uv pip install -e ".[dev]"
pytest                                                    # unit tests, no external services needed

docker compose -f deploy/docker-compose.yml up --build    # full stack incl. Postgres, Redis, dependency-stub
```
