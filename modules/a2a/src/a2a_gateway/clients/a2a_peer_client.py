"""A2A Peer Client (LLD stack table: JSON-RPC-2.0-over-HTTP, the A2A
spec's own wire shape). Calls an arbitrary external agent's own A2A
endpoint (`message/send`) and its Agent Card well-known endpoint.

Not a `ResilientHTTPClient` subclass: that base class assumes one fixed
`base_url` per client instance, while this one calls a different
absolute URL per target agent on a single shared `httpx.AsyncClient` —
the same shape of problem MCP's own backend client (Module 21) already
solved, and the same answer: each target agent gets its **own** circuit
breaker (`_breaker_for`), so one struggling peer never trips delegation
to a different one.

Deliberately excluded from this platform's service-to-service JWT auth
(security/jwt_auth.py): this client calls arbitrary external A2A agents,
not a platform peer module — those agents have their own (possibly
nonexistent, possibly entirely different) auth scheme, matching MCP's
own backend client exclusion for the identical reason.
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

import httpx
from aiobreaker import CircuitBreaker, CircuitBreakerError
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

__all__ = ["A2APeerHTTPClient", "A2APeerRpcError", "CircuitBreakerError"]

_DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)
_WELL_KNOWN_CARD_PATH = "/.well-known/agent.json"
_RPC_PATH = "/v1/a2a/rpc"


class A2APeerRpcError(Exception):
    """A target agent's own A2A endpoint returned a JSON-RPC error object."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


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


class A2APeerHTTPClient:
    def __init__(self, client: httpx.AsyncClient | None = None, *, fail_max: int = 5) -> None:
        self._client = client or httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)
        self._fail_max = fail_max
        self._breakers: dict[str, CircuitBreaker] = {}

    def _breaker_for(self, agent_url: str) -> CircuitBreaker:
        if agent_url not in self._breakers:
            self._breakers[agent_url] = CircuitBreaker(
                fail_max=self._fail_max, timeout_duration=timedelta(seconds=30.0), name=agent_url,
            )
        return self._breakers[agent_url]

    async def _do_get(self, url: str) -> httpx.Response:
        resp = await self._client.get(url)
        resp.raise_for_status()
        return resp

    async def _do_post(self, url: str, payload: dict[str, Any]) -> httpx.Response:
        resp = await self._client.post(url, json=payload)
        resp.raise_for_status()
        return resp

    @_with_retry()
    async def _get(self, agent_url: str, path: str) -> httpx.Response:
        url = agent_url.rstrip("/") + path
        return await self._breaker_for(agent_url).call_async(self._do_get, url)

    @_with_retry()
    async def _post(self, agent_url: str, path: str, payload: dict[str, Any]) -> httpx.Response:
        url = agent_url.rstrip("/") + path
        return await self._breaker_for(agent_url).call_async(self._do_post, url, payload)

    async def fetch_agent_card(self, agent_url: str) -> dict[str, Any]:
        resp = await self._get(agent_url, _WELL_KNOWN_CARD_PATH)
        return resp.json()

    async def send_message(self, agent_url: str, *, skill_id: str, input_message: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": "message/send",
            "params": {"skill_id": skill_id, "message": input_message},
        }
        resp = await self._post(agent_url, _RPC_PATH, payload)
        data = resp.json()
        if data.get("error"):
            err = data["error"]
            raise A2APeerRpcError(err.get("code", -32000), err.get("message", "peer returned a JSON-RPC error"))
        return data.get("result", {})
