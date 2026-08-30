"""Unit tests for the intent step (ticket #82's IntentDetectionClient port,
core/neural.py's NeuralStepExecutor._execute_intent_step)."""
from __future__ import annotations

import pytest

from workflow_engine.core.domain import RetryPolicy, StepStatus, WorkflowNode
from workflow_engine.core.fakes import (
    StubAgenticRAGClient,
    StubGuardrailsClient,
    StubIntentDetectionClient,
    StubLLMGatewayClient,
    StubToolOrchestrationClient,
)
from workflow_engine.core.neural import NeuralStepExecutor

pytestmark = pytest.mark.asyncio


def _intent_node(intent_ref: str = "classify") -> WorkflowNode:
    return WorkflowNode(
        id="intent_step", type="task", execution_mode="neural",
        config={"intent_ref": intent_ref}, retry_policy=RetryPolicy(),
    )


async def test_intent_step_calls_intent_detection_and_returns_top_intent():
    intent_detection = StubIntentDetectionClient()
    intent_detection.set_response("Where's my order #A1029?", "order_status", 0.92)
    executor = NeuralStepExecutor(
        StubLLMGatewayClient(), StubToolOrchestrationClient(), StubGuardrailsClient(),
        intent_detection=intent_detection,
    )

    outcome = await executor.execute(
        _intent_node(), context={"message": "Where's my order #A1029?"}, tenant_id="acme", trace_id="trace-1",
    )

    assert outcome.status == StepStatus.COMPLETED
    assert outcome.output == {"intent": "order_status"}
    assert outcome.confidence_score == 0.92
    assert intent_detection.calls == [{"message": "Where's my order #A1029?", "tenant_id": "acme"}]


async def test_intent_step_bypasses_guardrails_and_llm_gateway():
    """The intent step must not touch guardrails/llm_gateway/tool_orchestration
    at all -- classifying the raw message is not itself an agent action with
    a side effect to screen, unlike an agent_ref-driven neural step."""
    llm_gateway = StubLLMGatewayClient()
    intent_detection = StubIntentDetectionClient(default_intent="policy_question", default_confidence=0.8)
    executor = NeuralStepExecutor(
        llm_gateway, StubToolOrchestrationClient(), StubGuardrailsClient(), intent_detection=intent_detection,
    )

    outcome = await executor.execute(
        _intent_node(), context={"message": "What's your return policy?"}, tenant_id="acme", trace_id="trace-1",
    )

    assert outcome.status == StepStatus.COMPLETED
    assert llm_gateway.calls == []


async def test_intent_step_without_a_wired_client_fails_cleanly():
    executor = NeuralStepExecutor(
        StubLLMGatewayClient(), StubToolOrchestrationClient(), StubGuardrailsClient(), intent_detection=None,
    )

    outcome = await executor.execute(_intent_node(), context={"message": "hi"}, tenant_id="acme", trace_id="trace-1")

    assert outcome.status == StepStatus.FAILED
    assert "IntentDetectionClient" in outcome.error


def _rag_node(rag_ref: str = "retrieve") -> WorkflowNode:
    return WorkflowNode(
        id="rag_step", type="task", execution_mode="neural",
        config={"rag_ref": rag_ref}, retry_policy=RetryPolicy(),
    )


async def test_rag_step_calls_agentic_rag_and_returns_synthesized_context():
    agentic_rag = StubAgenticRAGClient()
    agentic_rag.set_response(
        "What's your return policy?",
        {"synthesized_context": "Returns are accepted within 30 days.", "groundedness_score": 0.93},
    )
    executor = NeuralStepExecutor(
        StubLLMGatewayClient(), StubToolOrchestrationClient(), StubGuardrailsClient(), agentic_rag=agentic_rag,
    )

    outcome = await executor.execute(
        _rag_node(), context={"message": "What's your return policy?"}, tenant_id="acme", trace_id="trace-1",
    )

    assert outcome.status == StepStatus.COMPLETED
    assert outcome.output == {"synthesized_context": "Returns are accepted within 30 days.", "groundedness_score": 0.93}
    assert outcome.confidence_score == 0.93
    assert agentic_rag.calls == [{"query": "What's your return policy?", "tenant_id": "acme"}]


async def test_rag_step_without_a_wired_client_fails_cleanly():
    executor = NeuralStepExecutor(
        StubLLMGatewayClient(), StubToolOrchestrationClient(), StubGuardrailsClient(), agentic_rag=None,
    )

    outcome = await executor.execute(_rag_node(), context={"message": "hi"}, tenant_id="acme", trace_id="trace-1")

    assert outcome.status == StepStatus.FAILED
    assert "AgenticRAGClient" in outcome.error


async def test_agent_ref_neural_step_is_unaffected_by_intent_detection_being_none():
    """Every pre-existing neural step (agent_ref-driven) must behave exactly
    as before this change, whether or not intent_detection is wired."""
    llm_gateway = StubLLMGatewayClient()
    llm_gateway.set_response("a1", {"content": "hello"}, 0.9)
    executor = NeuralStepExecutor(
        llm_gateway, StubToolOrchestrationClient(), StubGuardrailsClient(), intent_detection=None,
    )
    node = WorkflowNode(
        id="s1", type="task", execution_mode="neural", config={"agent_ref": "a1"}, retry_policy=RetryPolicy(),
    )

    outcome = await executor.execute(node, context={}, tenant_id="acme", trace_id="trace-1")

    assert outcome.status == StepStatus.COMPLETED
    assert outcome.output == {"content": "hello"}
    assert outcome.confidence_score == 0.9
