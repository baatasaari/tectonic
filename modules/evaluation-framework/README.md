# Evaluation Framework — Module 18

Scores agent outputs against faithfulness, coherence, tool-trace
correctness and domain-specific metrics, both as a CI/CD gate before
deployment and as continuous sampling against live production traffic.
Full design doc:
[`../../docs/module-18-evaluation-framework.md`](../../docs/module-18-evaluation-framework.md).

## Layout

```
src/evaluation_framework/
  main.py                 FastAPI app, lifespan wiring, /healthz, /metrics
  app_context.py           Process-wide dependency container
  config.py                 Pydantic Settings — LLD config schema
  core/
    domain.py                EvalRun/MetricScore/GateResult/DomainMetricPack dataclasses
    ports.py                   Repository, LLM Gateway
    fakes.py                     In-memory implementations of every port, for unit tests
    similarity.py                  Term-frequency cosine similarity — the heuristic-fallback's basis
    metric_adapters.py               Heuristic metrics (coherence, tool-trace, domain packs) + LLM-judge fallback
    deepeval_adapter.py                Real `deepeval.metrics.FaithfulnessMetric` integration
    evaluator.py                       Orchestrates a metric set against one agent output
    gate_engine.py                      Aggregates MetricScores into a pass/fail GateResult
    sampler.py                           Production Sampler — deterministic hash-based sampling
  cli/main.py               `agenteval run --gate` — CI/CD pipeline entrypoint
  db/                      SQLAlchemy 2.0 async models + repository
  clients/                 HTTP client for LLM Gateway (LLM-as-judge fallback)
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI router — evaluate, gate, domain-packs, scores, sample
  schemas/                    Pydantic request/response models
```

## Design notes vs. the LLD

- **Eval library adapters — `faithfulness` is real DeepEval, corrected
  after review.** The LLD calls for wrapping DeepEval, Ragas and an
  OpenAI-Evals-compatible format behind one interface. The first version
  of this module assumed DeepEval "pulls in heavy dependency trees
  (torch, transformer model downloads) unsuited to this module's offline
  unit-test tier" and reimplemented faithfulness as a term-overlap
  heuristic instead of using it — that assumption was never actually
  verified and turned out to be wrong: `deepeval` installs in a few
  seconds with ~35 lightweight dependencies (no torch, no local models;
  its LLM-as-judge calls go through a small `DeepEvalBaseLLM` interface
  you implement). `core/deepeval_adapter.py` now genuinely wraps the real
  `deepeval.metrics.FaithfulnessMetric`, via `DeepEvalLLMGatewayModel`
  routing every one of DeepEval's internal judge calls through this
  module's own LLM Gateway client — consistent with the platform rule
  that LLM Gateway is the only module allowed to call a model provider
  directly. `core/metric_adapters.py`'s original term-overlap
  implementation (`HeuristicFaithfulnessMetric`) is kept as the automatic
  fallback when the real DeepEval call fails (LLM Gateway unreachable,
  unparseable model output) — the same real-call-for-the-common-case,
  documented-fallback-for-the-degraded-case pattern used elsewhere in
  this platform. `coherence` and `tool_trace_correctness` remain local
  heuristics — DeepEval has no equivalent off-the-shelf metric worth
  wrapping for either. Ragas remains unintegrated; the technique proven
  here for DeepEval would apply equally to it. Any metric name covered by
  neither DeepEval nor this local registry falls back to an LLM Gateway
  LLM-as-judge call, preserving the LLD's "multiple metric sources
  feeding one interface" shape.
- **Testing DeepEval offline.** `deepeval`'s metric classes make several
  internal LLM calls per evaluation (extract truths, extract claims,
  judge each claim, summarise a reason) using its own prompt templates —
  real prompts, not a mock of DeepEval itself. The unit tests
  (`test_deepeval_adapter.py`) and the dependency-stub
  (`stubs/dependency-stub/app.py`'s `/v1/complete`) both script responses
  to those exact templates, computing per-claim verdicts from real
  token-overlap recall against the retrieval context rather than a fixed
  canned answer — an unfaithful claim genuinely scores lower than a
  faithful one in these tests, the same as it would against a real
  backing model.
- **Domain-specific metrics.** The LLD says these are "ported directly
  from AgentEval's existing custom metrics" — that codebase isn't
  available in this build environment, so `financial_guidance_compliance`
  is a fresh, simple reimplementation of the same intent (checks for a
  disclaimer, flags guaranteed-return language), not a port.
- **Production sampler.** The LLD specifies a Kafka consumer sampling
  live traffic. This module has no Kafka broker to consume from in this
  build (the same Kafka-to-HTTP substitution used elsewhere in this
  platform, e.g. Sentinel Agents' event ingestion) — `POST
  /v1/evaluation-framework/sample` is the HTTP substitute. The actual
  sampling decision (`core/sampler.py`) is still a real, testable
  component: a deterministic hash of `interaction_id` against the
  configured `sample_rate`, not `random()`, so a given interaction always
  samples the same way.
- **Pagination on `GET /scores`.** Added `limit`/`offset` query params
  (default 50, max 200) and a `MetricScoreListResponse` envelope
  (`items`/`total`/`limit`/`offset`) — this endpoint previously returned
  every matching score row unbounded, a real scaling gap for a tenant
  with a large evaluation history. Ordered by `created_at` descending
  (newest score first) for stable pagination.
- **CLI.** `agenteval run --gate` reimplements the LLD's described
  AgentEval CLI pattern against this module's own HTTP API (`click` +
  `httpx`, both real, lightweight dependencies) rather than porting
  AgentEval's actual CLI code, which isn't available here.
- **Feedback loop to LLM Gateway / Context Engineering / PromptOps.**
  The LLD's sequence diagram has those modules query this module's
  Postgres directly for recent quality scores. Every module in this
  platform owns its own database (ports-and-adapters, no cross-module DB
  access), so that feedback loop is `GET /v1/evaluation-framework/scores`
  being polled by those modules instead — the same data, reached through
  this module's API rather than its storage.

- **Connection pooling tuned to replica count.** SQLAlchemy's out-of-
  the-box defaults (`pool_size=5`, `max_overflow=10`) are the same
  regardless of how many pods are running — at this module's own
  `deploy/helm/evaluation-framework/values.yaml` `autoscaling.maxReplicas: 20`,
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

docker compose -f deploy/docker-compose.yml up --build    # full stack incl. Postgres, dependency-stub
```
