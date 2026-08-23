# Short-Term Memory — Module 12

Owns the working memory for a single active session: the recent message
buffer that the Conversational Engine and Context Engineering draw on
when assembling a prompt. Distinct from Long-Term Memory, which persists
across sessions; this module's data is scoped to one session's lifetime
and is intentionally lightweight. Full design doc:
[`../../docs/module-12-short-term-memory.md`](../../docs/module-12-short-term-memory.md).

## Layout

```
src/short_term_memory/
  main.py                 FastAPI app, lifespan wiring, /healthz, /metrics
  app_context.py           Process-wide dependency container
  config.py                 Pydantic Settings — LLD config schema
  core/
    domain.py                MessageRecord/BufferState/AppendResult dataclasses
    ports.py                   BufferStore, LLM Gateway summarisation client
    fakes.py                    In-memory implementations of every port, for unit tests
    salience_scorer.py            Salience Scorer — numbers/commitments/"remember this"/entity density
    tokenization.py                 Local token-count estimator
    buffer_manager.py                Buffer Manager — append, overflow detection, summarisation trigger
  clients/                 Redis adapter (literal LLD key patterns) + LLM Gateway HTTP client
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI router — sessions/{id}/messages, sessions/{id}
  schemas/                    Pydantic request/response models
```

No `db/` or `alembic/` here: the LLD's own data model section is "Redis
structures, not relational," and `clients/redis_buffer_store.py`
implements its three key patterns
(`stm:session:{id}:messages`/`:summary`/`:token_count`) literally.

## Design notes vs. the LLD

- **Salience scoring.** The LLD calls for "a lightweight rule-based
  scorer...with an optional LLM-based scorer for higher-value tenants."
  `core/salience_scorer.py` implements the rule-based tier in full
  (numeric content, named-commitment phrases, explicit "remember this"
  cues, and a capitalised-word entity-density proxy). The optional
  LLM-based tier is a `scoring_method: "llm_based"` config value with no
  implementation behind it yet — it's additive to the rule-based path
  the LLD frames as the common case, not a replacement, so it's left as
  a documented gap rather than a deviation requiring a stand-in.

## Running locally

```bash
uv venv && uv pip install -e ".[dev]"
pytest                                                    # unit tests, no external services needed

docker compose -f deploy/docker-compose.yml up --build    # full stack incl. Redis, dependency-stub
```
