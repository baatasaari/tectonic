"""Verifies the resilience primitives themselves: retry-with-backoff on
transient failures, no retry on client errors, and a circuit breaker that
actually opens (and short-circuits) after repeated failures — the same
checks run live against this module's real HTTPXyz clients during this
branch's development, kept here as permanent regression coverage."""
import httpx
import pytest
import respx

from evaluation_framework.clients.resilience import CircuitBreakerError, ResilientHTTPClient


class _Client(ResilientHTTPClient):
    def __init__(self, base_url: str, **kwargs):
        super().__init__(base_url, breaker_name="test-client", **kwargs)

    async def ping(self) -> dict:
        resp = await self._get("/ping")
        return resp.json()

    async def get_optional_thing(self) -> dict | None:
        resp = await self._get_optional("/maybe")
        return resp.json() if resp is not None else None


@respx.mock
async def test_retries_on_5xx_then_succeeds():
    route = respx.get("http://svc.local/ping")
    counter = {"n": 0}

    def flaky(request):
        counter["n"] += 1
        if counter["n"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"ok": True})

    route.mock(side_effect=flaky)
    client = _Client("http://svc.local")

    result = await client.ping()

    assert result == {"ok": True}
    assert counter["n"] == 3


@respx.mock
async def test_does_not_retry_on_4xx():
    counter = {"n": 0}

    def bad_request(request):
        counter["n"] += 1
        return httpx.Response(400, json={"error": "bad"})

    respx.get("http://svc.local/ping").mock(side_effect=bad_request)
    client = _Client("http://svc.local")

    with pytest.raises(httpx.HTTPStatusError):
        await client.ping()
    assert counter["n"] == 1


@respx.mock
async def test_circuit_breaker_opens_after_repeated_failures_and_short_circuits():
    counter = {"n": 0}

    def always_503(request):
        counter["n"] += 1
        return httpx.Response(503)

    respx.get("http://svc.local/ping").mock(side_effect=always_503)
    client = _Client("http://svc.local", fail_max=3, breaker_timeout_seconds=30.0)

    opened = False
    for _ in range(10):
        try:
            await client.ping()
        except CircuitBreakerError:
            opened = True
            break
        except httpx.HTTPStatusError:
            continue
    assert opened, "circuit breaker never opened after repeated 5xx failures"

    before = counter["n"]
    with pytest.raises(CircuitBreakerError):
        await client.ping()
    assert counter["n"] == before, "an open breaker must short-circuit without a real network call"


@respx.mock
async def test_get_optional_returns_none_on_404_without_raising():
    respx.get("http://svc.local/maybe").mock(return_value=httpx.Response(404))
    client = _Client("http://svc.local")

    result = await client.get_optional_thing()

    assert result is None


@respx.mock
async def test_get_optional_still_raises_on_non_404_error():
    respx.get("http://svc.local/maybe").mock(return_value=httpx.Response(500))
    client = _Client("http://svc.local")

    with pytest.raises(httpx.HTTPStatusError):
        await client.get_optional_thing()
