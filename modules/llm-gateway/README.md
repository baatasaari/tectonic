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

- **Connection pooling tuned to replica count.** SQLAlchemy's out-of-
  the-box defaults (`pool_size=5`, `max_overflow=10`) are the same
  regardless of how many pods are running — at this module's own
  `deploy/helm/llm-gateway/values.yaml` `autoscaling.maxReplicas: 30`,
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
- **Pagination on `GET /virtual-keys`.** Added `limit`/`offset` query
  params (default 50, max 200) and a `VirtualKeyListResponse` envelope
  (`items`/`total`/`limit`/`offset`) — virtual keys are tenant-scoped and
  accumulate over the life of a tenant, and this endpoint previously
  returned every matching row unbounded. Ordered by `created_at`
  descending (newest key first).
- **`GET /providers` deliberately left unpaginated.** Provider configs
  are a fixed, admin-configured set of LLM providers this gateway
  integrates with — one row per provider it knows how to call
  (OpenAI, Anthropic, etc.) — not a tenant-scoped dataset that grows
  with usage. `ProviderConfigRecord` has no `tenant_id` and
  `list_provider_configs()` takes no filters; in practice this is a
  handful of rows, so `limit`/`offset` would add API surface without a
  real bound to enforce. See the comment at the route in
  `api/routes_admin.py`. Revisit if provider configs ever become
  tenant-configurable.

## Running locally

```bash
uv venv && uv pip install -e ".[dev]"
pytest                                                    # unit tests, no external services needed

docker compose -f deploy/docker-compose.yml up --build    # full stack incl. Postgres, Redis, dependency-stub
```
