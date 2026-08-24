# LLM Gateway — Module 3

The only module permitted to call model providers directly. Every other
module that needs LLM inference goes through this gateway — never a
provider SDK directly — which is what makes provider swaps, cost governance
and quality routing possible platform-wide. Full design doc:
[`../../docs/module-03-llm-gateway.md`](../../docs/module-03-llm-gateway.md).

## Layout

```
src/llm_gateway/
  main.py                 FastAPI app, lifespan wiring, /healthz, /metrics
  app_context.py           Process-wide dependency container
  config.py                 Pydantic Settings — LLD config schema
  core/
    domain.py                VirtualKey/BudgetPolicy/RequestLog/ProviderConfig dataclasses
    ports.py                   Repository, cache, quality-score feed, provider client, secrets
    fakes.py                    In-memory implementations of every port, for unit tests
    normalizer.py                 Request Normalizer
    similarity.py                  Shared term-frequency cosine similarity for the cache
    semantic_cache.py               Semantic Cache — in-memory (tests) and Redis (prod) impls
    router.py                        Quality-Aware Router
    cost_governance.py                Cost Governance Engine
    failover.py                        Failover Manager
    gateway_service.py                  The request orchestrator (this module's "scheduler")
    deprecation_watcher.py               Model Deprecation Watcher
  db/                      SQLAlchemy 2.0 async models + repository
  clients/                 HTTP provider adapter, Redis quality-score store, Secrets client
  security/                 Service-to-service JWT bearer auth (shared signing key)
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI routers — OpenAI-compatible completions/embeddings, admin
  schemas/                    Pydantic request/response models
```

## Design notes vs. the LLD

- **Provider adapter.** The LLD names LiteLLM as the provider abstraction.
  `clients/http_provider_client.py` implements `ProviderClient` as a generic
  OpenAI-compatible HTTP adapter instead of importing the `litellm` package
  directly: every `ProviderConfig.endpoint` already models a per-provider
  base URL, and OpenAI-compatible `/chat/completions` is what the large
  majority of providers and proxies speak today — including LiteLLM's own
  proxy mode, so pointing a `ProviderConfig` at a running LiteLLM proxy is a
  drop-in way to get its 100+-provider coverage. Swapping in the `litellm`
  Python SDK directly means implementing the same `ProviderClient` Protocol
  against `litellm.acompletion` — same boundary Module 1 draws around ADK.
- **Semantic cache.** RedisVL (real embeddings + ANN search) is the LLD's
  production choice; `core/similarity.py` implements a lightweight local
  term-frequency cosine similarity instead, so caching works without a
  network round-trip to an embedding model on every lookup. Staleness
  awareness is a `stale` flag per entry a drift-detection signal can set
  (`flag_stale`/`invalidate_stale`), rather than a fixed TTL.
- **Quality-aware router.** Cost and latency aren't separately tracked
  fields in the LLD's `ProviderConfig` data model, so the router uses each
  provider's `priority` as a shared proxy for both, blended with the live
  quality score from the (stubbed, until Module built) Evaluation
  Framework feed per the configured strategy weights.
- **Cost governance.** Implements optimistic reserve-then-settle: an
  estimated ceiling is reserved against the budget before the provider call
  (so two concurrent requests can't both slip under a limit that only one
  should), then settled to the real cost once the provider responds.
- **Service-to-service JWT auth.** Before this, no module authenticated
  any of its inbound HTTP calls — any process able to reach a module's
  port could call it, and every outbound call this module makes to a
  platform peer carried no credential at all. `security/jwt_auth.py` adds
  shared-signing-key (HS256) bearer auth: `ServiceAuthMiddleware` verifies
  every inbound request's `Authorization: Bearer <JWT>` against this
  module's own `service_name` as the required audience (except
  `/healthz` and `/metrics` — Kubernetes probes and Prometheus scraping
  carry no auth token); `ServiceBearerAuth` (an `httpx.Auth` flow) mints a
  fresh, short-lived (5 min default) token scoped via the `aud` claim to
  the *specific* peer being called on every outbound request
  `HTTPSecretsClient` makes to Secrets and Credential Management (not yet
  built in this platform — same aspirational-target pattern used
  elsewhere) — a token minted to call one peer is rejected if replayed
  against a different one. `HTTPProviderClient` is deliberately excluded:
  it calls real external LLM provider APIs, not a platform peer, and
  those already authenticate via their own API keys. The shared secret
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

docker compose -f deploy/docker-compose.yml up --build    # full stack incl. Postgres, Redis, dependency-stub
```
