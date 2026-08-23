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
    similarity.py                  Term-frequency cosine similarity — the FaithfulnessMetric's basis
    metric_adapters.py               Eval Library Adapters + Domain-Specific Metrics
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

- **Eval library adapters.** The LLD calls for wrapping DeepEval, Ragas
  and an OpenAI-Evals-compatible format behind one interface. Those
  libraries pull in heavy dependency trees (transformer model downloads
  in particular) unsuited to this module's offline unit-test tier.
  `core/metric_adapters.py` implements `faithfulness` (term-overlap
  cosine similarity, the same lightweight approach Guardrails' and
  Agentic RAG's groundedness checks use — a parallel implementation, not
  shared code), `coherence` (a repetition/redundancy heuristic — a
  deliberately narrower signal than a real coherence model, documented
  as such) and `tool_trace_correctness` (error-free-call ratio) as local
  heuristics behind the same `EvalMetric` protocol a real DeepEval/Ragas
  adapter would satisfy. Any metric name not in that local registry falls
  back to an LLM Gateway LLM-as-judge call, preserving the LLD's
  "multiple metric sources feeding one interface" shape.
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

## Running locally

```bash
uv venv && uv pip install -e ".[dev]"
pytest                                                    # unit tests, no external services needed

docker compose -f deploy/docker-compose.yml up --build    # full stack incl. Postgres, dependency-stub
```
