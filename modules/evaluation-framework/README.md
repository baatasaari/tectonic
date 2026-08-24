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
  security/                 Service-to-service JWT bearer auth (shared signing key)
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
- **Service-to-service JWT auth.** Before this, no module authenticated
  any of its inbound HTTP calls — any process able to reach a module's
  port could call it, and every outbound call this module makes carried
  no credential at all. `security/jwt_auth.py` adds shared-signing-key
  (HS256) bearer auth: `ServiceAuthMiddleware` verifies every inbound
  request's `Authorization: Bearer <JWT>` against this module's own
  `service_name` as the required audience (except `/healthz` and
  `/metrics` — Kubernetes probes and Prometheus scraping carry no auth
  token); `ServiceBearerAuth` (an `httpx.Auth` flow) mints a fresh,
  short-lived (5 min default) token scoped via the `aud` claim to the
  *specific* peer being called on every outbound request this module's
  `HTTPLLMGatewayClient` makes — a token minted to call one peer is
  rejected if replayed against a different one. The shared secret
  (`TECTONIC_JWT_SHARED_SECRET`, one Kubernetes Secret referenced by
  every module's Helm chart under this same literal env var name, not a
  per-module-prefixed one) defaults to an obviously-insecure placeholder
  for zero-config local dev/tests; `main.py` logs a startup warning if
  it's still active. This is service-to-service auth for inter-module
  calls, not the platform's external-facing user-auth story — a real API
  gateway/OAuth layer in front of the platform's own entry points is a
  separate, larger concern, out of scope here.

## Running locally

```bash
uv venv && uv pip install -e ".[dev]"
pytest                                                    # unit tests, no external services needed

docker compose -f deploy/docker-compose.yml up --build    # full stack incl. Postgres, dependency-stub
```
