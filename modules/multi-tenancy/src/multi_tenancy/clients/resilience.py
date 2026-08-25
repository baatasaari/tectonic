"""Resiliency for this module's outbound HTTP calls to platform peers
(every registered isolation-probe target).

Real, off-the-shelf libraries, not hand-rolled: `tenacity` for
retry-with-exponential-backoff, `aiobreaker` for the circuit breaker (the
standard "Release It!" pattern — the same choice every other module in
this platform has already made).

Only retries what's actually safe to retry: a network-level failure
(connection reset, DNS failure) or a 5xx response, both of which mean
"the server didn't process this, try again" — never a 4xx, which means
"the server processed this and rejected it," where retrying just repeats
the same mistake against a peer that may itself be retry-storming.

`ResilientHTTPClient` is the base class every fixed-base_url client in
this module's `clients/` should inherit from: `self._get(path, ...)` /
`self._post(path, ...)` replace direct `self._client.get/post(...)`
calls and get retry + circuit-breaking for free. Each registered probe
target gets its own `HTTPTenantScopedListClient` instance (one fixed
base_url apiece, per its own config entry), so no per-target-URL breaker
variant is needed even though this module talks to many different peers.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

import httpx
from aiobreaker import CircuitBreaker, CircuitBreakerError
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)

__all__ = ["DEFAULT_TIMEOUT", "CircuitBreakerError", "ResilientHTTPClient"]


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


class ResilientHTTPClient:
    """Base class for this module's fixed-base_url outbound HTTP clients.
    Every call made through `_get`/`_post`/`_put`/`_delete` gets
    exponential-backoff retry on transient failures and a per-client
    circuit breaker that opens after repeated failures — so a struggling
    peer gets a break instead of a retry storm, and callers fail fast
    instead of piling up on a peer that's already down."""

    def __init__(
        self, base_url: str, *, client: httpx.AsyncClient | None = None,
        timeout: httpx.Timeout | None = None, breaker_name: str = "http-client",
        fail_max: int = 5, breaker_timeout_seconds: float = 30.0,
        auth: httpx.Auth | None = None,
    ) -> None:
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=timeout or DEFAULT_TIMEOUT, auth=auth)
        self._breaker = CircuitBreaker(
            fail_max=fail_max, timeout_duration=timedelta(seconds=breaker_timeout_seconds), name=breaker_name,
        )

    async def _do_request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        # raise_for_status() must run *inside* the breaker-tracked call, not after it --
        # otherwise a 5xx response (call_async sees no exception) never counts as a
        # breaker failure, and the circuit would never open no matter how many 5xxs a
        # peer returns. Only a raised exception counts toward fail_max.
        resp = await self._client.request(method, path, **kwargs)
        resp.raise_for_status()
        return resp

    @_with_retry()
    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        return await self._breaker.call_async(self._do_request, method, path, **kwargs)

    async def _get(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self._request("GET", path, **kwargs)

    async def _get_optional(self, path: str, **kwargs: Any) -> httpx.Response | None:
        """Like `_get`, but a 404 is returned as `None` instead of raising — for
        endpoints where "not found" is an expected outcome, not an error."""
        try:
            return await self._get(path, **kwargs)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise

    async def _post(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self._request("POST", path, **kwargs)

    async def _put(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self._request("PUT", path, **kwargs)

    async def _delete(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self._request("DELETE", path, **kwargs)
