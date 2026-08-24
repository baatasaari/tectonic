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

Deliberately excluded from this platform's service-to-service JWT auth
(security/jwt_auth.py): this client calls real external LLM provider APIs
(OpenAI, Anthropic, etc.), not a platform peer module. Those providers
authenticate via their own API keys (see `_auth_headers`/`SecretsClient`
above), which have nothing to do with the shared HS256 signing key every
platform module holds for calling *each other*.
"""
from __future__ import annotations

import httpx

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
        self._client = client or httpx.AsyncClient(timeout=30.0)

    def set_providers(self, providers: dict[str, ProviderConfigRecord]) -> None:
        self._providers = providers

    async def _auth_headers(self, provider: str, tenant_id: str) -> dict[str, str]:
        if self._secrets is None:
            return {}
        api_key = await self._secrets.get_provider_api_key(provider, tenant_id)
        return {"Authorization": f"Bearer {api_key}"} if api_key else {}

    async def complete(
        self, *, provider: str, model: str, messages: list[ChatMessage], tenant_id: str
    ) -> CompletionResult:
        config = self._providers.get(provider)
        if config is None:
            raise ProviderError(provider, "no ProviderConfig registered for this provider")

        try:
            resp = await self._client.post(
                f"{config.endpoint}/chat/completions",
                json={"model": model, "messages": [{"role": m.role, "content": m.content} for m in messages]},
                headers={"X-Tenant-Id": tenant_id, **await self._auth_headers(provider, tenant_id)},
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
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
            resp = await self._client.post(
                f"{config.endpoint}/embeddings",
                json={"model": model, "input": text},
                headers={"X-Tenant-Id": tenant_id, **await self._auth_headers(provider, tenant_id)},
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise ProviderError(provider, str(e)) from e

        return resp.json()["data"][0]["embedding"]
