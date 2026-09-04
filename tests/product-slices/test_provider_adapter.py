from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import httpx
import pytest

adapter_path = (
    Path(__file__).resolve().parents[2]
    / "scripts/product-slice-stubs/provider_adapter.py"
)
adapter_spec = importlib.util.spec_from_file_location(
    "pilot_provider_adapter", adapter_path
)
if adapter_spec is None or adapter_spec.loader is None:
    raise RuntimeError(f"cannot import {adapter_path}")
adapter = importlib.util.module_from_spec(adapter_spec)
sys.modules[adapter_spec.name] = adapter
adapter_spec.loader.exec_module(adapter)


def settings(**overrides):
    values = {
        "mode": "openai",
        "base_url": "https://provider.example/v1",
        "api_key": "secret-key",
        "chat_model": "provider-model",
        "embedding_model": "embedding-model",
    }
    values.update(overrides)
    return adapter.ProviderSettings(**values)


def test_mock_mode_needs_no_provider_credentials():
    settings(mode="mock", base_url="", api_key="", chat_model="").validate()


def test_real_mode_requires_complete_credentials():
    with pytest.raises(adapter.ProviderConfigurationError):
        settings(api_key="").validate()


def test_real_remote_endpoint_requires_https():
    with pytest.raises(adapter.ProviderConfigurationError):
        settings(base_url="http://provider.example/v1").validate()


@pytest.mark.parametrize(
    ("logical_model", "payload"),
    [
        (
            "order-lookup-agent",
            {"content": "", "tool_arguments": {"order_id": "A1029"}},
        ),
        ("refund-extractor-agent", {"content": "", "refund_amount": 25.5}),
        ("rag-groundedness-critic", {"content": "", "score": 0.92, "gaps": ""}),
        ("rag-query-reformulator", {"content": "", "revised_query": "return policy"}),
        ("compose-response-agent", {"content": "Your order has shipped."}),
    ],
)
def test_task_contracts_accept_valid_payloads(logical_model, payload):
    assert (
        adapter.validate_structured_output(logical_model, json.dumps(payload))
        == payload
    )


def test_task_contract_rejects_invalid_payload():
    with pytest.raises(adapter.ProviderResponseError):
        adapter.validate_structured_output(
            "rag-groundedness-critic", '{"content":"","score":2,"gaps":""}'
        )


@pytest.mark.asyncio
async def test_real_completion_maps_logical_model_without_leaking_key():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "real-1",
                "choices": [{"message": {"content": '{"content":"Done"}'}}],
                "usage": {"prompt_tokens": 4, "completion_tokens": 2},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await adapter.real_chat_completion(
            {
                "model": "compose-response-agent",
                "messages": [{"role": "user", "content": "{}"}],
            },
            settings(),
            client,
        )

    assert captured["authorization"] == "Bearer secret-key"
    assert captured["body"]["model"] == "provider-model"
    assert "secret-key" not in json.dumps(result)
    assert result["model"] == "compose-response-agent"
