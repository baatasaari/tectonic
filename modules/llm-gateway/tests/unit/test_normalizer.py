import pytest

from llm_gateway.core.normalizer import NormalizationError, normalize_chat_request


def test_valid_request_normalizes():
    raw = {"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]}
    req = normalize_chat_request(raw, tenant_id="tenant-a", virtual_key_id="vk-1")
    assert req.model == "gpt-4o"
    assert req.messages[0].role == "user"
    assert req.task_type == "chat"


def test_missing_model_rejected():
    with pytest.raises(NormalizationError):
        normalize_chat_request({"messages": [{"role": "user", "content": "hi"}]}, tenant_id="t", virtual_key_id="vk")


def test_empty_messages_rejected():
    with pytest.raises(NormalizationError):
        normalize_chat_request({"model": "gpt-4o", "messages": []}, tenant_id="t", virtual_key_id="vk")


def test_malformed_message_rejected():
    with pytest.raises(NormalizationError):
        normalize_chat_request({"model": "gpt-4o", "messages": [{"role": "user"}]}, tenant_id="t", virtual_key_id="vk")


def test_routing_hints_carry_task_type():
    raw = {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "hi"}],
        "routing_hints": {"task_type": "summarization"},
    }
    req = normalize_chat_request(raw, tenant_id="t", virtual_key_id="vk")
    assert req.task_type == "summarization"
