# Guardrails — Module 14

The dual-stage policy enforcement point for every input reaching an LLM
and every output leaving one. Every module that calls LLM Gateway routes
the request and response through this module first (input check before
the call, output check after). Full design doc:
[`../../docs/module-14-guardrails.md`](../../docs/module-14-guardrails.md).

## Layout

```
src/guardrails/
  main.py                 FastAPI app, lifespan wiring, /healthz, /metrics
  app_context.py           Process-wide dependency container
  config.py                 Pydantic Settings — LLD config schema
  core/
    domain.py                PolicyProfile/InterventionLog/RedTeamRun/BypassIncident dataclasses
    ports.py                   Repository, LLM Gateway, Sentinel Agents
    fakes.py                    In-memory implementations of every port, for unit tests
    pii_detector.py               Presidio PII Detector — regex/heuristic detection + redaction
    jailbreak_detector.py           Jailbreak/Injection Detector — strong patterns + ambiguous fallback
    similarity.py                    Term-frequency cosine similarity — the Groundedness Checker's basis
    groundedness_checker.py           Groundedness Checker
    policy_engine.py                   NeMo Guardrails Policy Engine — the check orchestrator
    red_team.py                         Red-Team Self-Test Job
  db/                      SQLAlchemy 2.0 async models + repository
  clients/                 HTTP clients for LLM Gateway + Sentinel Agents
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI router — check, policy-profiles, red-team-runs
  schemas/                    Pydantic request/response models
```

## Design notes vs. the LLD

- **Policy engine.** The LLD calls for NVIDIA NeMo Guardrails as the
  policy execution engine. NeMo Guardrails' rails/flow DSL and its model
  runtime requirements are a large dependency footprint unsuited to this
  module's offline unit-test tier. `core/policy_engine.py` implements the
  same "orchestrate checks per policy profile" responsibility directly,
  in Python, against this module's own `PolicyProfile` config shape.
- **PII detection.** The LLD calls for Microsoft Presidio. Presidio pulls
  in spaCy language models (a multi-hundred-MB download on first use) —
  a network dependency this module's unit-test tier shouldn't carry.
  `core/pii_detector.py` implements regex/heuristic detection and
  redaction for the LLD's example entity types (EMAIL, PHONE_NUMBER,
  CREDIT_CARD, plus SSN) directly, plus a coarse capitalised-word-pair
  heuristic for PERSON — deliberately approximate (real named-entity
  recognition needs a real model), documented as such rather than
  silently claimed equivalent to Presidio's coverage.
- **Jailbreak/injection detection.** The LLD calls for "pattern
  detectors, a fine-tuned classifier, and an LLM Gateway call for
  ambiguous cases." The fine-tuned-classifier tier is replaced with a
  second, weaker pattern tier: strong patterns block immediately, weak
  signal words are ambiguous and deferred to the LLM Gateway fallback —
  preserving the LLD's layered-defence shape (multiple independent
  signals feeding one decision) without a trained model.
- **Groundedness checking.** The LLD calls for logic "shared...with
  Agentic RAG's Groundedness Critic." No shared library exists between
  modules in this build, so `core/groundedness_checker.py` is a parallel
  implementation of the same term-frequency-cosine-similarity approach
  Agentic RAG's Heuristic Groundedness Critic uses — the same idea, not
  literally shared code.
- **`context` field.** The LLD's documented `/check` request shape
  (`text, stage, policy_profile_id`) has no field for the context an
  output should be grounded against, which groundedness checking can't
  function without. `context` is accepted as an additional optional
  field.
- **Zero-config default profile.** The LLD's `/check` endpoint accepts an
  optional `policy_profile_id` but doesn't say what happens with none
  configured yet for a tenant. When omitted and no policy profile exists,
  this module falls back to an ephemeral profile built directly from its
  own YAML config defaults, so `/check` works immediately without
  requiring a `POST /policy-profiles` call first.
- **Pagination on `GET /red-team-runs`.** Added `limit`/`offset` query
  params (default 50, max 200) and a `RedTeamRunListResponse` envelope
  (`items`/`total`/`limit`/`offset`) — this endpoint previously returned
  every matching row unbounded, a real scaling gap for a tenant with a
  large red-team run history. Ordered by `run_at` descending (newest run
  first) for stable pagination.

- **Connection pooling tuned to replica count.** SQLAlchemy's out-of-
  the-box defaults (`pool_size=5`, `max_overflow=10`) are the same
  regardless of how many pods are running — at this module's own
  `deploy/helm/guardrails/values.yaml` `autoscaling.maxReplicas: 30`,
  that's up to 450 connections to this module's own Postgres
  instance from this module alone at full autoscale, with no one having
  deliberately decided that number. `db/session.py`'s `make_engine` now
  passes explicit, configurable `pool_size=4` /
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

docker compose -f deploy/docker-compose.yml up --build    # full stack incl. Postgres, dependency-stub
```
