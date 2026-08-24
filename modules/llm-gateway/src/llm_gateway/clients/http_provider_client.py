"""ProviderClient adapter (LLD stack table: LiteLLM Provider Adapter Layer).

Implemented here as a generic OpenAI-compatible HTTP adapter rather than a
hard dependency on the `litellm` package: every `ProviderConfig.endpoint`
already models a per-provider base URL (LLD §3.1), and OpenAI-compatible
`/chat/completions` is what the overwhelming majority of providers/gateways
speak today — including LiteLLM's own proxy mode, so pointing a
ProviderConfig's endpoint at a running LiteLLM proxy is a drop-in way to get
its 100+-provider coverage without this module importing the library
directly. Swapping in the `litellm` Python SDK directly means implementing
this same `ProviderClient` Protocol against `litellm.acompletion` — the
router, failover manager and cost governance engine that drive this port
don't change either way, same boundary Module 1 draws around ADK.

**Resiliency.** Every call is retried with exponential backoff (network
errors / 5xx only, never 4xx) and tracked by a circuit breaker — the same
`tenacity` + `aiobreaker` primitives `clients/resilience.py` uses elsewhere
in this module, but not `ResilientHTTPClient` itself: that base class
assumes one fixed `base_url` per client, while this one calls a different
absolute URL per provider (`config.endpoint`) on a single shared
`httpx.AsyncClient`. Each provider therefore gets its **own** circuit
breaker (`_breaker_for`) — Provider A being down must never trip requests
to Provider B, which is also exactly what this module's own quality-aware
routing and failover manager need: a per-provider health signal, not one
global one.
"""
from __future__ import annotations

from datetime import timedelta

import httpx
from aiobreaker import CircuitBreaker, CircuitBreakerError
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from llm_gateway.core.domain import (
    ChatMessage,
    CompletionResult,
    ProviderConfigRecord,
    ProviderError,
)
from llm_gateway.core.ports import SecretsClient

# Rough per-1k-token pricing used to estimate cost when a provider's
# response doesn't echo it back (many OpenAI-compatible endpoints don't).
# Real pricing should come from the provider's own billing API or a
# maintained price table; this is a placeholder default, not a claim of
# accuracy.
_DEFAULT_COST_PER_1K_TOKENS = 0.002

_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return isinstance(exc, (httpx.TransportError, httpx.TimeoutException))


def _with_retry(max_attempts: int = 3):
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=0.2, min=0.2, max=2.0),
        retry=retry_if_exception(_is_retryable),
        reraise=True,
    )


class HTTPProviderClient:
    def __init__(
        self,
        providers: dict[str, ProviderConfigRecord],
        secrets: SecretsClient | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """`providers` maps provider_name -> its ProviderConfigRecord (for
        endpoint lookup); refresh it whenever provider configs change."""
        self._providers = providers
        self._secrets = secrets
        self._client = client or httpx.AsyncClient(timeout=_TIMEOUT)
        self._breakers: dict[str, CircuitBreaker] = {}

    def set_providers(self, providers: dict[str, ProviderConfigRecord]) -> None:
        self._providers = providers

    def _breaker_for(self, provider: str) -> CircuitBreaker:
        if provider not in self._breakers:
            self._breakers[provider] = CircuitBreaker(
                fail_max=5, timeout_duration=timedelta(seconds=30), name=f"provider-{provider}",
            )
        return self._breakers[provider]

    async def _auth_headers(self, provider: str, tenant_id: str) -> dict[str, str]:
        if self._secrets is None:
            return {}
        api_key = await self._secrets.get_provider_api_key(provider, tenant_id)
        return {"Authorization": f"Bearer {api_key}"} if api_key else {}

    @_with_retry()
    async def _do_post(self, url: str, **kwargs) -> httpx.Response:
        resp = await self._client.post(url, **kwargs)
        resp.raise_for_status()
        return resp

    async def _post(self, provider: str, url: str, **kwargs) -> httpx.Response:
        return await self._breaker_for(provider).call_async(self._do_post, url, **kwargs)

    async def complete(
        self, *, provider: str, model: str, messages: list[ChatMessage], tenant_id: str
    ) -> CompletionResult:
        config = self._providers.get(provider)
        if config is None:
            raise ProviderError(provider, "no ProviderConfig registered for this provider")

        try:
            resp = await self._post(
                provider,
                f"{config.endpoint}/chat/completions",
                json={"model": model, "messages": [{"role": m.role, "content": m.content} for m in messages]},
                headers={"X-Tenant-Id": tenant_id, **await self._auth_headers(provider, tenant_id)},
            )
        except (httpx.HTTPError, CircuitBreakerError) as e:
            raise ProviderError(provider, str(e)) from e

        data = resp.json()
        choice = data["choices"][0]["message"]
        usage = data.get("usage", {})
        input_tokens = usage.get("prompt_tokens", sum(len(m.content.split()) for m in messages))
        output_tokens = usage.get("completion_tokens", len(choice["content"].split()))
        cost = usage.get("cost", (input_tokens + output_tokens) / 1000 * _DEFAULT_COST_PER_1K_TOKENS)

        return CompletionResult(
            content=choice["content"],
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
            model_used=data.get("model", model),
        )

    async def embed(self, *, provider: str, model: str, text: str, tenant_id: str) -> list[float]:
        config = self._providers.get(provider)
        if config is None:
            raise ProviderError(provider, "no ProviderConfig registered for this provider")

        try:
            resp = await self._post(
                provider,
                f"{config.endpoint}/embeddings",
                json={"model": model, "input": text},
                headers={"X-Tenant-Id": tenant_id, **await self._auth_headers(provider, tenant_id)},
            )
        except (httpx.HTTPError, CircuitBreakerError) as e:
            raise ProviderError(provider, str(e)) from e

        return resp.json()["data"][0]["embedding"]
